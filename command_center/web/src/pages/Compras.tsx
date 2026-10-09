/* Pedidos internos e Compras (dono, 30/09: "siga com a tela de pedidos e compras").
 *
 * Pedido é de quem precisa: o mecânico pede a peça pelo celular. Compra é de quem gasta: o
 * gerente junta pedidos e o que está abaixo do mínimo numa compra do fornecedor. Receber a
 * compra dá entrada no estoque sozinho — ninguém redigita o que chegou.
 *
 * 30/09: os e-mails de compra do urace@ viram compras sozinhos, e envio / pagamento /
 * entrega atualizam a compra (providers/compras_email.py).
 */
import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { useGet } from '../api/hooks'
import { useItemNaRota } from '../api/rota'
import type { Client } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { Chip, Empty, ErrorState, Loading, PageHeader, Scrim, Section } from '../components/ui'
import { Icon } from '../components/Icon'
import { useToast } from '../components/Toast'
import { Picker } from '../components/Unir'
import { tr, LOCALE } from '../i18n'

interface Pedido { id: number; item_id: number | null; description: string; qty: number; unit: string; client_id: number | null; cliente: string | null
  needed_by: string | null; urgent: number; notes: string | null; status: string; purchase_id: number | null; pedido_por: string | null; created_at: string
  envio?: string | null; rastreio?: string | null; transportadora?: string | null; fornecedor?: string | null }
interface Linha { id: number; item_id: number | null; description: string; qty: number; qty_received: number; unit_cost: number | null; request_id: number | null
  item: string | null; unit: string | null; pedido_por: string | null; cliente: string | null }
interface Evento { id: number; purchase_id?: number; kind: string; stage?: string | null; at: string | null; subject: string | null; sender: string | null
  order_number: string | null; invoice_number?: string | null; tracking: string | null; carrier: string | null; amount: number | null
  link: string | null; url?: string | null; mailbox?: string | null }
interface Sugerido { id: number; description: string; qty: number; unit: string; pedido_por: string | null; cliente: string | null; por_sku: boolean }
interface Compra { id: number; supplier: string; status: string; reference: string | null; ordered_at: string | null; expected_at: string | null; notes: string | null
  criada_por: string | null; created_at: string; linhas: Linha[]; total: number | null; sem_custo: number; atrasada: boolean
  source?: string; order_number?: string | null; tracking?: string | null; carrier?: string | null; ship_status?: string | null
  paid_at?: string | null; shipped_at?: string | null; delivered_at?: string | null; email_total?: number | null; items_hint?: string | null
  eventos?: Evento[]; pedidos_sugeridos?: Sugerido[]; entregue_sem_entrada?: boolean
  invoice_number?: string | null; payment_status?: string | null; amount_due?: number | null; order_url?: string | null
  asana_gid?: string | null; asana_error?: string | null }
interface Repor { id: number; name: string; unit: string; falta: number; sku: string | null; supplier_url: string | null }
interface Resumo { pedidos_abertos: number; urgentes: number; rascunhos: number; a_caminho: number; atrasadas: number; entregues?: number
  a_pagar?: number; repor: Repor[] }
interface ItemEst { id: number; name: string; unit: string; nosso: number; cost?: number | null; category: string }
interface Local { code: string; name: string }

const ST_PEDIDO: Record<string, [string, 'warn' | 'info' | 'ok' | 'neutral' | 'accent']> = {
  aberto: ['aberto', 'warn'], comprando: ['comprando', 'info'], chegou: ['chegou', 'accent'], entregue: ['entregue', 'ok'], cancelado: ['cancelado', 'neutral'] }
const ST_COMPRA: Record<string, [string, 'warn' | 'info' | 'ok' | 'neutral' | 'accent']> = {
  rascunho: ['rascunho', 'neutral'], pedida: ['pedida', 'info'], parcial: [tr("chegou em parte"), 'accent'], recebida: ['recebida', 'ok'], cancelada: ['cancelada', 'neutral'] }
// andamento da ENTREGA, lido dos e-mails da loja/transportadora — não é o status do estoque
const ST_ENVIO: Record<string, [string, 'warn' | 'info' | 'ok' | 'neutral' | 'accent' | 'crit']> = {
  pedido: [tr("pedido feito"), 'neutral'], pago: ['pago', 'info'], enviado: [tr("a caminho"), 'info'], entregue: ['entregue', 'accent'], cancelado: [tr("cancelado na loja"), 'crit'] }
const EV: Record<string, string> = { pedido: tr("Pedido"), pagamento: tr("Pagamento"), envio: tr("Envio"), entregue: tr("Entregue"), cancelado: tr("Cancelado"), reembolso: tr("Reembolso") }
// a etapa fina que o e-mail (ou a página de rastreio) disse — dono, 06/10: "se está em rota, se já foi entregue, se teve alguma atualização"
const ETAPA: Record<string, [string, 'warn' | 'info' | 'ok' | 'neutral' | 'accent' | 'crit']> = {
  pagamento_pendente: [tr("pagamento pendente"), 'warn'], preparando: ['preparando', 'neutral'], mensagem: [tr("mensagem da loja"), 'neutral'],
  etiqueta: [tr("etiqueta criada"), 'info'], em_transito: [tr("em trânsito"), 'info'], previsao: [tr("previsão de entrega"), 'info'],
  saiu_para_entrega: [tr("saiu para entrega"), 'accent'], atraso: [tr("atraso na entrega"), 'crit'] }
const TOM_EV: Record<string, 'warn' | 'info' | 'ok' | 'neutral' | 'accent' | 'crit'> = { entregue: 'accent', cancelado: 'crit', envio: 'info', pagamento: 'ok', reembolso: 'warn' }
function rotuloEvento(e: Evento): [string, 'warn' | 'info' | 'ok' | 'neutral' | 'accent' | 'crit'] {
  if (e.stage && ETAPA[e.stage]) return ETAPA[e.stage]
  return [EV[e.kind] || e.kind, TOM_EV[e.kind] || 'neutral']
}
const ultimoEvento = (c: Compra) => (c.eventos || []).length ? (c.eventos as Evento[])[(c.eventos as Evento[]).length - 1] : null
const hostDe = (url: string) => { try { return new URL(url).hostname.replace(/^www\./, '') } catch { return 'link' } }
export function linkRastreio(n: string, transp?: string | null) {
  const t = (transp || '').toLowerCase(), u = n.toUpperCase()
  if (u.startsWith('1Z') || t === 'ups') return `https://www.ups.com/track?tracknum=${encodeURIComponent(n)}`
  if (t === 'fedex') return `https://www.fedex.com/fedextrack/?trknbr=${encodeURIComponent(n)}`
  if (t === 'usps') return `https://tools.usps.com/go/TrackConfirmAction?tLabels=${encodeURIComponent(n)}`
  if (t === 'dhl') return `https://www.dhl.com/us-en/home/tracking/tracking-express.html?tracking-id=${encodeURIComponent(n)}`
  return null
}
function Rastreios({ tracking, carrier }: { tracking?: string | null; carrier?: string | null }) {
  if (!tracking) return null
  return <>{tracking.split(/\s+/).filter(Boolean).map(n => { const url = linkRastreio(n, carrier)
    return <span key={n} className="small">{carrier ? `${carrier} ` : ''}{url ? <a href={url} target="_blank" rel="noreferrer">{n}</a> : n}</span> })}</>
}
// o sistema roda no fuso da Flórida (dono): o e-mail chega em UTC e é mostrado em Orlando
const horaFL = (iso: string) => { const d = new Date(iso); return isNaN(d.getTime()) ? iso
  : d.toLocaleString(LOCALE(), { timeZone: 'America/New_York', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }).replace(',', '') }
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
    if (!(q > 0)) { toast(tr("Quantidade maior que zero."), 'warn'); return }
    if (modo === 'estoque' ? !item : !desc.trim()) { toast(tr("Diga o que precisa."), 'warn'); return }
    setIndo(true)
    try {
      await api.post('/compras/pedidos', { item_id: modo === 'estoque' ? item!.id : null, description: modo === 'livre' ? desc.trim() : null,
        qty: q, unit: modo === 'livre' ? unidade : null, needed_by: quando || null, urgent: urgente, client_id: cliente?.id ?? null, notes: nota.trim() || null })
      toast(tr("Pedido feito. Quem compra já vê na fila."), 'ok'); onDone(); onClose()
    } catch (e) { toast((e as ApiError).message, 'crit') } finally { setIndo(false) }
  }

  return <Scrim onMouseDown={onClose}><div className="modal" style={{ maxWidth: 560 }} onMouseDown={e => e.stopPropagation()}>
    <h3>{tr("Novo pedido")}</h3>
    <div className="seg" style={{ marginBottom: 10 }}>
      <button className={`btn sm${modo === 'estoque' ? '' : ' ghost'}`} onClick={() => setModo('estoque')}>{tr("Peça do estoque")}</button>
      <button className={`btn sm${modo === 'livre' ? '' : ' ghost'}`} onClick={() => setModo('livre')}>{tr("Outra coisa")}</button>
    </div>
    {modo === 'estoque'
      ? item ? <div className="row gap" style={{ alignItems: 'center', marginBottom: 12 }}><b className="grow">{item.name}</b>
          <span className="small muted">{tr("tem")} {item.nosso} {item.unit}</span><button className="btn ghost sm" onClick={() => setItem(null)}>{tr("trocar")}</button></div>
        : <label className="fld"><span>{tr("Qual peça")}</span>
          <input value={busca} onChange={e => setBusca(e.target.value)} placeholder={tr("digite o nome (2 letras)")} autoFocus />
          {achados.length > 0 && <div className="tbl">{achados.map(i => <button key={i.id} className="tr" style={{ textAlign: 'left', width: '100%', background: 'none', border: 0, cursor: 'pointer', color: 'inherit' }}
            onClick={() => { setItem(i); setUnidade(i.unit) }}><span className="grow">{i.name}</span><span className="small muted">{tr("tem")} {i.nosso} {i.unit}</span></button>)}</div>}
          {busca.trim().length >= 2 && !achados.length && <span className="small muted">{tr("Não está no estoque — use \"Outra coisa\".")}</span>}
        </label>
      : <label className="fld"><span>{tr("O que precisa")}</span><input value={desc} onChange={e => setDesc(e.target.value)} placeholder={tr("Fita de freio, chave 10mm…")} autoFocus /></label>}
    <div className="row gap wrap">
      <label className="fld grow"><span>{tr("Quantidade")}</span><input type="number" inputMode="decimal" min={0} value={qtd} onChange={e => setQtd(e.target.value)} /></label>
      {modo === 'livre' && <label className="fld grow"><span>{tr("Unidade")}</span><input value={unidade} onChange={e => setUnidade(e.target.value)} /></label>}
      <label className="fld grow"><span>{tr("Para quando")}</span><input type="date" value={quando} onChange={e => setQuando(e.target.value)} /></label>
    </div>
    <label className="check" style={{ margin: '0 0 12px' }}><input type="checkbox" checked={urgente} onChange={e => setUrgente(e.target.checked)} /> {tr("Urgente")} <span className="small muted">{tr("(entra em \"Precisa de atenção\")")}</span></label>
    <Picker label={tr("Para o kart de (opcional)")} value={cliente} onPick={setCliente} />
    <label className="fld"><span>{tr("Nota")}</span><input value={nota} onChange={e => setNota(e.target.value)} placeholder={tr("qual kart, modelo, link")} /></label>
    <div className="modal-foot"><button className="btn ghost" onClick={onClose}>{tr("Cancelar")}</button>
      <button className="btn" disabled={indo} onClick={salvar}>{indo ? tr("Enviando…") : tr("Pedir")}</button></div>
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
    try { await api.post(`/compras/pedidos/${p.id}/${qual}`); toast(qual === 'cancelar' ? tr("Pedido cancelado.") : tr("Entregue a quem pediu."), 'ok'); lista.reload() }
    catch (e) { toast((e as ApiError).message, 'crit') }
  }

  return <>
    <PageHeader title={tr("Pedidos")} help={tr("O que a equipe PRECISA que se compre (a lista de desejos). Quem compra junta os pedidos numa compra; aí o pedido mostra o envio e avisa quando chegou.")}>
      {gerente && marcados.length > 0 && <button className="btn" onClick={() => nav(`/compras?pedidos=${marcados.join(',')}`)}>{tr("Comprar")} {marcados.length} {tr("pedido(s)")}</button>}
      {can('OPERATOR') && <button className="btn primary" onClick={() => setNovo(true)}><Icon name="plus" size={16} /> {tr("Novo pedido")}</button>}
    </PageHeader>
    <div className="seg" style={{ marginBottom: 12 }}>
      {[['aberto', 'Abertos'], ['comprando', 'Comprando'], ['chegou', 'Chegou'], ['entregue', 'Entregues'], ['cancelado', 'Cancelados'], ['', 'Todos']].map(([k, r]) =>
        <button key={k} className={`btn sm${filtro === k ? '' : ' ghost'}`} onClick={() => { setFiltro(k); setMarcados([]) }}>{r}</button>)}
    </div>
    {lista.error && <ErrorState error={lista.error} retry={lista.reload} />}
    {lista.loading && !lista.data && <Loading />}
    {lista.data && (!lista.data.pedidos.length
      ? <Empty title={tr("Nenhum pedido aqui")}>{filtro === 'aberto' ? <>{tr("Precisa de algo?")} <b>{tr("Novo pedido")}</b>.</> : null}</Empty>
      : <div className="card"><div className="tbl">{lista.data.pedidos.map(p => {
        const [rot, tom] = ST_PEDIDO[p.status] || [p.status, 'neutral']
        return <div className="tr" key={p.id}>
          {gerente && p.status === 'aberto' && <input type="checkbox" aria-label={tr("comprar {0}", p.description)} checked={marcados.includes(p.id)}
            onChange={() => setMarcados(m => m.includes(p.id) ? m.filter(x => x !== p.id) : [...m, p.id])} />}
          <div className="grow">
            <b>{p.qty}{tr("×")} {p.description}</b> {!!p.urgent && <Chip tone="crit">{tr("urgente")}</Chip>}
            <div className="small muted">{p.pedido_por || '—'} · {dia(p.created_at)}{p.cliente ? tr(" · kart de {0}", p.cliente) : ''}{p.needed_by ? tr(" · até {0}", dia(p.needed_by)) : ''}
              {p.purchase_id ? <> · <Link to={`/compras/${p.purchase_id}`}>{tr("compra #")}{p.purchase_id}</Link></> : null}{p.notes ? ` · ${p.notes}` : ''}</div>
            {p.status === 'comprando' && p.rastreio && <div className="row gap wrap"><Rastreios tracking={p.rastreio} carrier={p.transportadora} /></div>}
          </div>
          {p.status === 'comprando' && p.envio && ST_ENVIO[p.envio] && <Chip tone={ST_ENVIO[p.envio][1]}>{ST_ENVIO[p.envio][0]}</Chip>}
          <Chip tone={tom}>{rot}</Chip>
          {p.status === 'aberto' && (gerente || p.pedido_por === user?.name) && <button className="btn ghost sm" onClick={() => acao(p, 'cancelar')}>{tr("cancelar")}</button>}
          {p.status === 'chegou' && <button className="btn sm" onClick={() => acao(p, 'entregue')}>{tr("entreguei")}</button>}
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
    if (!corpo.length) { toast(tr("Ponha pelo menos um item."), 'warn'); return }
    setIndo(true)
    try {
      const r = await api.post<{ id: number }>('/compras', { supplier: fornecedor, reference: ref || null, expected_at: previsao || null, pedir, linhas: corpo })
      toast(pedir ? tr("Compra #{0} registrada como pedida.", r.id) : tr("Rascunho #{0} salvo.", r.id), 'ok'); onDone(r.id); onClose()
    } catch (e) { toast((e as ApiError).message, 'crit') } finally { setIndo(false) }
  }

  return <Scrim onMouseDown={onClose}><div className="modal" style={{ maxWidth: 720 }} onMouseDown={e => e.stopPropagation()}>
    <h3>{tr("Nova compra")}</h3>
    <label className="fld"><span>{tr("Fornecedor")}</span><input value={fornecedor} onChange={e => setFornecedor(e.target.value)} list="fornecedores" />
      <datalist id="fornecedores"><option value="Comet Kart Sales" /><option value="KartSport (IAME)" /><option value="Tillotson" /><option value="Harbor Freight" /></datalist></label>
    <div className="stack" style={{ gap: 8 }}>
      {linhas.map(l => <div key={l.chave} className="row gap wrap" style={{ alignItems: 'flex-end', paddingBottom: 8, borderBottom: '1px solid var(--glass-line)' }}>
        <label className="fld grow" style={{ flexBasis: 240, margin: 0 }}><span>{l.request_id ? tr("Pedido #{0}", l.request_id) : tr("Item")}</span>
          <select value={l.item_id ?? ''} onChange={e => { const id = e.target.value ? Number(e.target.value) : null; const it = itens.find(i => i.id === id)
            muda(l.chave, { item_id: id, description: id ? '' : l.description, unit_cost: l.unit_cost || (it?.cost != null ? String(it.cost) : '') }) }}>
            <option value="">{tr("— fora do estoque (escreva abaixo) —")}</option>
            {itens.map(i => <option key={i.id} value={i.id}>{i.name}</option>)}
          </select>
          {!l.item_id && <input value={l.description} onChange={e => muda(l.chave, { description: e.target.value })} placeholder={tr("o que é")} style={{ marginTop: 6 }} />}
        </label>
        <label className="fld" style={{ width: 90, margin: 0 }}><span>{tr("Qtd")}</span><input type="number" inputMode="decimal" min={0} value={l.qty} onChange={e => muda(l.chave, { qty: e.target.value })} /></label>
        <label className="fld" style={{ width: 120, margin: 0 }}><span>{tr("Custo unit.")}</span><input type="number" inputMode="decimal" min={0} value={l.unit_cost} onChange={e => muda(l.chave, { unit_cost: e.target.value })} placeholder="$" /></label>
        <button className="btn ghost sm" aria-label={tr("tirar item")} onClick={() => setLinhas(ls => ls.filter(x => x.chave !== l.chave))}>✕</button>
      </div>)}
      <button className="btn ghost sm" style={{ alignSelf: 'flex-start' }} onClick={() => setLinhas(ls => [...ls, nova({})])}><Icon name="plus" size={14} /> {tr("item")}</button>
    </div>
    <div className="row gap wrap" style={{ marginTop: 12 }}>
      <label className="fld grow"><span>{tr("Nº do pedido / rastreio")}</span><input value={ref} onChange={e => setRef(e.target.value)} /></label>
      <label className="fld grow"><span>{tr("Previsão de chegada")}</span><input type="date" value={previsao} onChange={e => setPrevisao(e.target.value)} /></label>
    </div>
    <label className="check"><input type="checkbox" checked={pedir} onChange={e => setPedir(e.target.checked)} /> {tr("Já pedi ao fornecedor")} <span className="small muted">{tr("(senão fica como rascunho)")}</span></label>
    <div className="modal-foot"><span className="grow small">{tr("Total:")} <b>{usd(total)}</b></span>
      <button className="btn ghost" onClick={onClose}>{tr("Cancelar")}</button>
      <button className="btn" disabled={indo} onClick={salvar}>{indo ? tr("Salvando…") : pedir ? tr("Registrar compra") : tr("Salvar rascunho")}</button></div>
  </div></Scrim>
}

/* Compra que nasceu de e-mail vem sem itens: quem comprou diz o que foi — da ficha do estoque,
 * escrito à mão, ou ligando os pedidos da equipe (que já têm quantidade e quem pediu). */
function PorItens({ id, itens, sugeridos, onDone }: { id: number; itens: ItemEst[]; sugeridos: Sugerido[]; onDone: () => void }) {
  const toast = useToast()
  const abertos = useGet<{ pedidos: Pedido[] }>('/compras/pedidos?status=aberto')
  const [linhas, setLinhas] = useState<LinhaNova[]>([])
  const [ligar, setLigar] = useState<number[]>([])
  const [indo, setIndo] = useState(false)
  const muda = (k: string, c: Partial<LinhaNova>) => setLinhas(ls => ls.map(l => l.chave === k ? { ...l, ...c } : l))
  const sugIds = new Set(sugeridos.map(x => x.id))
  const outros = (abertos.data?.pedidos || []).filter(p => !sugIds.has(p.id))

  async function salvar() {
    const corpo = linhas.filter(l => l.item_id || l.description.trim()).map(l => ({ item_id: l.item_id, description: l.description.trim() || null,
      qty: Number(l.qty.replace(',', '.')) || null, unit_cost: l.unit_cost.trim() ? Number(l.unit_cost.replace(',', '.')) : null }))
    if (!corpo.length && !ligar.length) { toast(tr("Escolha um pedido ou ponha um item."), 'warn'); return }
    setIndo(true)
    try {
      if (ligar.length) await api.post(`/compras/${id}/pedidos`, { request_ids: ligar })
      if (corpo.length) await api.post(`/compras/${id}/linhas`, corpo)
      toast(tr("Itens na compra."), 'ok'); setLinhas([]); setLigar([]); abertos.reload(); onDone()
    } catch (e) { toast((e as ApiError).message, 'crit') } finally { setIndo(false) }
  }
  const marca = (rid: number) => setLigar(m => m.includes(rid) ? m.filter(x => x !== rid) : [...m, rid])

  return <div className="stack" style={{ gap: 8, marginTop: 12, paddingTop: 12, borderTop: '1px solid var(--glass-line)' }}>
    <b>{tr("O que veio nesta compra")}</b>
    {sugeridos.length > 0 && <div><div className="small muted" style={{ marginBottom: 4 }}>{tr("Pedidos da equipe que aparecem no e-mail da loja:")}</div>
      <div className="tbl">{sugeridos.map(p => <label className="tr" key={p.id} style={{ cursor: 'pointer' }}>
        <input type="checkbox" checked={ligar.includes(p.id)} onChange={() => marca(p.id)} />
        <div className="grow"><b>{p.qty}{tr("×")} {p.description}</b><div className="small muted">{p.pedido_por || '—'}{p.cliente ? tr(" · kart de {0}", p.cliente) : ''}</div></div>
        <Chip tone="accent">{tr("parece ser")}</Chip></label>)}</div></div>}
    {outros.length > 0 && <label className="fld" style={{ margin: 0 }}><span>{tr("Ligar outro pedido aberto")}</span>
      <select value="" onChange={e => { const v = Number(e.target.value); if (v) marca(v) }}>
        <option value="">{tr("— escolha —")}</option>
        {outros.map(p => <option key={p.id} value={p.id}>{ligar.includes(p.id) ? '✓ ' : ''}#{p.id} · {p.qty}{tr("×")} {p.description}{p.pedido_por ? ` (${p.pedido_por})` : ''}</option>)}
      </select></label>}
    {ligar.filter(x => !sugIds.has(x)).length > 0 && <span className="small">{tr("Vai ligar:")} {ligar.filter(x => !sugIds.has(x)).map(x => `#${x}`).join(', ')}</span>}
    {linhas.map(l => <div key={l.chave} className="row gap wrap" style={{ alignItems: 'flex-end' }}>
      <label className="fld grow" style={{ flexBasis: 220, margin: 0 }}><span>{tr("Item")}</span>
        <select value={l.item_id ?? ''} onChange={e => { const v = e.target.value ? Number(e.target.value) : null; const it = itens.find(i => i.id === v)
          muda(l.chave, { item_id: v, unit_cost: l.unit_cost || (it?.cost != null ? String(it.cost) : '') }) }}>
          <option value="">{tr("— fora do estoque (escreva abaixo) —")}</option>
          {itens.map(i => <option key={i.id} value={i.id}>{i.name}</option>)}
        </select>
        {!l.item_id && <input value={l.description} onChange={e => muda(l.chave, { description: e.target.value })} placeholder={tr("o que é")} style={{ marginTop: 6 }} />}</label>
      <label className="fld" style={{ width: 80, margin: 0 }}><span>{tr("Qtd")}</span><input type="number" inputMode="decimal" min={0} value={l.qty} onChange={e => muda(l.chave, { qty: e.target.value })} /></label>
      <label className="fld" style={{ width: 110, margin: 0 }}><span>{tr("Custo unit.")}</span><input type="number" inputMode="decimal" min={0} value={l.unit_cost} onChange={e => muda(l.chave, { unit_cost: e.target.value })} placeholder="$" /></label>
      <button className="btn ghost sm" aria-label={tr("tirar item")} onClick={() => setLinhas(ls => ls.filter(x => x.chave !== l.chave))}>✕</button>
    </div>)}
    <div className="row gap wrap">
      <button className="btn ghost sm" onClick={() => setLinhas(ls => [...ls, nova({})])}><Icon name="plus" size={14} /> {tr("item")}</button>
      <span className="grow" />
      {(linhas.length > 0 || ligar.length > 0) && <button className="btn sm" disabled={indo} onClick={salvar}>{indo ? tr("Salvando…") : tr("Pôr na compra")}</button>}
    </div>
  </div>
}

function LinhaDoTempo({ eventos, id }: { eventos: Evento[]; id: number }) {
  if (!eventos.length) return null
  return <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid var(--glass-line)' }}>
    <h4 style={{ fontSize: 'inherit', margin: 0 }}>{tr("Linha do tempo")}</h4>
    <div className="small muted">{tr("Cada e-mail da loja, da transportadora e cada leitura da página de rastreio, na ordem em que chegaram.")}</div>
    <div className="tbl" style={{ marginTop: 6 }}>{eventos.map(e => { const [rot, tom] = rotuloEvento(e)
      return <div className="tr" key={e.id}>
        <Chip tone={tom}>{rot}</Chip>
        <div className="grow" style={{ minWidth: 0, overflowWrap: 'anywhere' }}>{e.link ? <a href={e.link} target="_blank" rel="noreferrer">{e.subject || tr("(sem assunto)")}</a> : e.subject}
          <div className="small muted">{e.at ? horaFL(e.at) : ''}{e.mailbox === 'web' ? tr(" · página de rastreio") : e.sender ? ` · ${e.sender.replace(/<.*>/, '').trim()}` : ''}
            {e.tracking ? ` · ${e.tracking}` : ''}{e.invoice_number ? tr(" · fatura {0}", e.invoice_number) : ''}
            {e.purchase_id && e.purchase_id !== id ? tr(" · mesma caixa de outra compra") : ''}
            {e.url && <> · <a href={e.url} target="_blank" rel="noreferrer">{tr("abrir")} {hostDe(e.url)}</a></>}</div></div>
      </div> })}</div>
  </div>
}

function FichaCompra({ id, gerente, locais, itens, onClose, onDone }: { id: number; gerente: boolean; locais: Local[]; itens: ItemEst[]; onClose: () => void; onDone: () => void }) {
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
    <h3>{tr("Compra #")}{d.id} · {d.supplier}</h3>
    <div className="row gap wrap" style={{ marginBottom: 10 }}>
      <Chip tone={tom}>{rot}</Chip>{d.atrasada && <Chip tone="crit">{tr("atrasada")}</Chip>}
      {d.reference && <span className="small muted">{tr("ref.")} {d.reference}</span>}
      {d.expected_at && <span className="small muted">{tr("previsão")} {dia(d.expected_at)}</span>}
      {gerente && d.total != null && d.linhas.length > 0 && <span className="small">{tr("total")} <b>{usd(d.total)}</b>{d.sem_custo ? tr(" + {0} sem custo", d.sem_custo) : ''}</span>}
    </div>
    {(d.ship_status || d.tracking || d.source === 'email') && <div className="row gap wrap" style={{ marginBottom: 10, alignItems: 'center' }}>
      {d.source === 'email' && <Chip tone="neutral">{tr("veio do e-mail")}</Chip>}
      {d.ship_status && ST_ENVIO[d.ship_status] && <Chip tone={ST_ENVIO[d.ship_status][1]}>{ST_ENVIO[d.ship_status][0]}</Chip>}
      {d.payment_status === 'pendente' && <Chip tone="warn">{tr("pagamento pendente")}{gerente && d.amount_due != null ? ` · ${usd(d.amount_due)}` : ''}</Chip>}
      {d.payment_status === 'pago' && <Chip tone="ok">{tr("pago")}</Chip>}
      {d.order_number && d.order_number !== d.reference && <span className="small muted">{tr("pedido")} {d.order_number}</span>}
      {d.invoice_number && <span className="small muted">{tr("fatura")} {d.invoice_number}</span>}
      <Rastreios tracking={d.tracking} carrier={d.carrier} />
      {gerente && d.email_total != null && <span className="small">{tr("a loja cobrou")} <b>{usd(d.email_total)}</b></span>}
    </div>}
    {(() => { const u = ultimoEvento(d); if (!u) return null; const [rot] = rotuloEvento(u)
      return <div className="small" style={{ marginBottom: 8 }}>{tr("Última atualização:")} <b>{rot}</b>{u.at ? ` · ${horaFL(u.at)}` : ''}</div> })()}
    {(d.order_url || d.asana_gid) && <div className="row gap wrap small" style={{ marginBottom: 10 }}>
      {d.order_url && <a href={d.order_url} target="_blank" rel="noreferrer">{tr("página do pedido (")}{hostDe(d.order_url)})</a>}
      {d.asana_gid && <a href={`https://app.asana.com/0/1215968721507536/${d.asana_gid}`} target="_blank" rel="noreferrer">{tr("tarefa no Shipping Orders")}</a>}
      {gerente && d.asana_error && <span className="muted">{tr("Asana:")} {d.asana_error}</span>}
    </div>}
    {d.items_hint && <div className="small" style={{ marginBottom: 8 }}>{tr("A loja disse:")} <b>{d.items_hint}</b></div>}
    {d.entregue_sem_entrada && <div className="small" style={{ marginBottom: 10, color: 'var(--warn, #b7791f)' }}>
      {tr("A transportadora entregou.")} {d.linhas.length ? tr("Confira a caixa e receba abaixo: é o que põe a peça no estoque.") : tr("Diga o que veio (ou ligue os pedidos) e receba — ou conclua, se não é de estoque.")}</div>}
    {!d.linhas.length && <div className="small muted" style={{ marginBottom: 8 }}>{tr("Sem itens ainda")}{gerente ? tr(" — ponha abaixo o que foi comprado.") : tr(". Quem comprou põe os itens.")}</div>}
    <div className="tbl">{d.linhas.map(l => {
      const falta = l.qty - l.qty_received
      return <div className="tr" key={l.id}>
        <div className="grow"><b>{l.item || l.description}</b>
          <div className="small muted">{l.qty_received}/{l.qty} {tr("recebido")}{gerente && l.unit_cost != null ? tr(" · {0} cada", usd(l.unit_cost)) : ''}
            {l.pedido_por ? tr(" · pedido por {0}", l.pedido_por) : ''}{l.cliente ? tr(" · kart de {0}", l.cliente) : ''}{!l.item_id ? tr(" · fora do estoque") : ''}</div>
          {aberta && falta > 0 && !l.item_id && <label className="check small"><input type="checkbox" checked={!!criar[l.id]} onChange={e => setCriar(x => ({ ...x, [l.id]: e.target.checked }))} /> {tr("criar ficha no estoque ao receber")}</label>}
        </div>
        {aberta && falta > 0 && <input className="inp" style={{ width: 80, minHeight: 36 }} type="number" inputMode="decimal" min={0} max={falta} aria-label={tr("quanto chegou de {0}", l.description)}
          value={receber[l.id] ?? ''} onChange={e => setReceber(x => ({ ...x, [l.id]: e.target.value }))} />}
        {falta <= 0 && <Chip tone="ok">{tr("completo")}</Chip>}
      </div>
    })}</div>

    {aberta && d.linhas.some(l => l.qty_received < l.qty) && <div className="row gap wrap" style={{ marginTop: 12, alignItems: 'flex-end' }}>
      {locais.length > 1 && <label className="fld" style={{ margin: 0 }}><span>{tr("Chegou em")}</span>
        <select value={local} onChange={e => setLocal(e.target.value)}>{locais.map(l => <option key={l.code} value={l.code}>{l.name}</option>)}</select></label>}
      <button className="btn primary" disabled={indo || !itensReceber.length}
        onClick={() => fazer('receber', { local, itens: itensReceber }, tr('Recebido: já entrou no estoque.'))}>{tr("Receber o que chegou")}</button>
    </div>}

    {gerente && aberta && <PorItens id={d.id} itens={itens} sugeridos={d.pedidos_sugeridos || []} onDone={recarregar} />}
    <LinhaDoTempo eventos={d.eventos || []} id={d.id} />

    {gerente && d.status === 'rascunho' && <div className="row gap wrap" style={{ marginTop: 14, alignItems: 'flex-end' }}>
      <label className="fld grow" style={{ margin: 0 }}><span>{tr("Nº do pedido / rastreio")}</span><input value={ref} onChange={e => setRef(e.target.value)} /></label>
      <label className="fld" style={{ margin: 0 }}><span>{tr("Previsão")}</span><input type="date" value={previsao} onChange={e => setPrevisao(e.target.value)} /></label>
      <button className="btn" disabled={indo} onClick={() => fazer('pedida', { reference: ref || null, expected_at: previsao || null }, 'Marcada como pedida.')}>{tr("Marcar como pedida")}</button>
    </div>}

    <div className="modal-foot">
      {gerente && aberta && !d.linhas.some(l => l.qty_received > 0) && <button className="btn ghost" disabled={indo}
        onClick={() => fazer('cancelar', {}, 'Compra cancelada; os pedidos voltaram para a fila.')}>{tr("Cancelar compra")}</button>}
      {gerente && aberta && <button className="btn ghost" disabled={indo} title={tr("Serviço, passe de pista, ferramenta que já foi para o uso")}
        onClick={() => { if (window.confirm(tr("Concluir sem dar entrada no estoque? Use para o que não é peça de estoque (serviço, passe de pista…)."))) fazer('concluir', {}, tr('Compra concluída.')) }}>{tr("Concluir sem estoque")}</button>}
      <span className="grow" />
      <button className="btn ghost" onClick={onClose}>{tr("Fechar")}</button>
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
  const [ficha, setFicha] = useItemNaRota('/compras', 'id', 'c')
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
    <PageHeader title={tr("Compras")} help={tr("O que a URACE comprou: pedido ao fornecedor, envio e chegada. Os e-mails de compra do urace@ entram aqui sozinhos, e cada envio/pagamento/entrega atualiza a compra. Receber dá entrada no estoque.")}>
      {gerente && selecionados > 0 && <button className="btn" onClick={comprarSelecionados}>{tr("Comprar")} {selecionados} {tr("selecionado(s)")}</button>}
      {gerente && <button className="btn primary" onClick={() => setNova([])}><Icon name="plus" size={16} /> {tr("Nova compra")}</button>}
    </PageHeader>

    {r && <div className="est-resumo">
      <Link to="/pedidos"><Chip tone={r.pedidos_abertos ? 'warn' : 'neutral'}>{r.pedidos_abertos} {tr("pedido(s) aberto(s)")}</Chip></Link>
      {!!r.urgentes && <Chip tone="crit">{r.urgentes} {tr("urgente(s)")}</Chip>}
      {!!r.repor.length && <Chip tone="warn">{r.repor.length} {tr("abaixo do mínimo")}</Chip>}
      {!!r.rascunhos && <Chip tone="neutral">{r.rascunhos} {tr("rascunho(s)")}</Chip>}
      <Chip tone="info">{r.a_caminho} {tr("a caminho")}</Chip>
      {!!r.atrasadas && <Chip tone="crit">{r.atrasadas} {tr("atrasada(s)")}</Chip>}
      {!!r.entregues && <Chip tone="warn">{r.entregues} {tr("entregue(s) sem entrada")}</Chip>}
      {!!r.a_pagar && <Chip tone="warn">{r.a_pagar} {tr("fatura(s) a pagar")}</Chip>}
    </div>}

    {gerente && !!pedidosAbertos.data?.pedidos.length && <Section title={tr("Pedidos esperando compra")} count={pedidosAbertos.data.pedidos.length}>
      <div className="tbl">{pedidosAbertos.data.pedidos.map(p => <label className="tr" key={p.id} style={{ cursor: 'pointer' }}>
        <input type="checkbox" checked={marcadosPed.includes(p.id)} onChange={() => setMarcadosPed(m => m.includes(p.id) ? m.filter(x => x !== p.id) : [...m, p.id])} />
        <div className="grow"><b>{p.qty}{tr("×")} {p.description}</b> {!!p.urgent && <Chip tone="crit">{tr("urgente")}</Chip>}
          <div className="small muted">{p.pedido_por || '—'}{p.cliente ? tr(" · kart de {0}", p.cliente) : ''}{p.needed_by ? tr(" · até {0}", dia(p.needed_by)) : ''}</div></div>
      </label>)}</div>
    </Section>}

    {!!r?.repor.length && <Section title={tr("Abaixo do mínimo")} count={r.repor.length}>
      <div className="tbl">{r.repor.map(x => <label className="tr" key={x.id} style={{ cursor: gerente ? 'pointer' : undefined }}>
        {gerente && <input type="checkbox" checked={marcadosRepor.includes(x.id)} onChange={() => setMarcadosRepor(m => m.includes(x.id) ? m.filter(y => y !== x.id) : [...m, x.id])} />}
        <div className="grow"><b>{x.name}</b>{x.sku && <span className="small muted"> {tr("· SKU")} {x.sku}</span>}</div>
        <span className="small">{tr("faltam")} <b>{x.falta}</b> {x.unit}</span>
        {x.supplier_url && <a className="btn ghost sm" href={x.supplier_url} target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()}>{tr("fornecedor")}</a>}
      </label>)}</div>
    </Section>}

    <Section title={tr("Compras")} count={compras.length} right={<div className="seg">
      {([['abertas', tr("Em aberto")], ['recebida', tr("Recebidas")], ['cancelada', tr("Canceladas")]] as const).map(([k, rot]) =>
        <button key={k} className={`btn sm${filtro === k ? '' : ' ghost'}`} onClick={() => setFiltro(k)}>{rot}</button>)}</div>}>
      {lista.error && <ErrorState error={lista.error} retry={lista.reload} />}
      {lista.loading && !lista.data && <Loading />}
      {lista.data && (!compras.length ? <Empty title={filtro === 'abertas' ? tr("Nenhuma compra em aberto") : tr("Nada aqui")} />
        : <div className="tbl">{compras.map(c => {
          const [rot, tom] = ST_COMPRA[c.status] || [c.status, 'neutral']
          return <div className="tr" key={c.id} role="button" tabIndex={0} style={{ cursor: 'pointer' }} onClick={() => setFicha(c.id)}
            onKeyDown={e => { if (e.key === 'Enter') setFicha(c.id) }}>
            <div className="grow" style={{ minWidth: 0 }}><b>#{c.id} · {c.supplier}</b>
              <div className="small muted">{c.linhas.length ? tr("{0} item(ns)", c.linhas.length) : tr("sem itens")}{c.items_hint ? ` · ${c.items_hint}` : ''}{c.reference ? tr(" · ref. {0}", c.reference) : ''}{c.tracking ? ` · ${c.carrier || 'rastreio'} ${c.tracking.split(' ')[0]}` : ''}{(() => { const u = ultimoEvento(c); return u?.at ? ` · atualizado ${horaFL(u.at)}` : '' })()}{c.expected_at ? tr(" · previsão {0}", dia(c.expected_at)) : ''} · {c.source === 'email' ? tr("veio do e-mail") : c.criada_por || '—'}</div></div>
            {gerente && (c.linhas.length ? c.total != null : c.email_total != null) && <span className="small">{usd(c.linhas.length ? c.total : c.email_total)}</span>}
            {c.atrasada && <Chip tone="crit">{tr("atrasada")}</Chip>}
            {c.payment_status === 'pendente' && ['pedida', 'parcial', 'rascunho'].includes(c.status) && <Chip tone="warn">{tr("a pagar")}</Chip>}
            {c.entregue_sem_entrada ? <Chip tone="warn">{tr("entregue · falta entrada")}</Chip>
              : (() => { const u = ultimoEvento(c); if (!['pedida', 'parcial', 'rascunho'].includes(c.status)) return null
                if (u?.stage && ETAPA[u.stage] && u.stage !== 'pagamento_pendente' && u.stage !== 'mensagem') return <Chip tone={ETAPA[u.stage][1]}>{ETAPA[u.stage][0]}</Chip>
                return c.ship_status && c.ship_status !== 'pedido' && ST_ENVIO[c.ship_status] ? <Chip tone={ST_ENVIO[c.ship_status][1]}>{ST_ENVIO[c.ship_status][0]}</Chip> : null })()}
            <Chip tone={tom}>{rot}</Chip>
          </div>
        })}</div>)}
    </Section>

    {nova_ !== null && <NovaCompra inicial={nova_} itens={est.data?.itens || []} onClose={() => setNova(null)} onDone={id => { recarregar(); setFicha(id) }} />}
    {ficha !== null && <FichaCompra id={ficha} gerente={gerente} locais={est.data?.locais || []} itens={est.data?.itens || []} onClose={() => setFicha(null)} onDone={recarregar} />}
  </>
}
