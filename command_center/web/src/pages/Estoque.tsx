/* Estoque — o que existe, onde está e de quem é.
 *
 * Decisões do dono que mandam nesta tela:
 *   22/09: chassi e motor têm ficha com número de série; pneu e peça são quantidade.
 *   23/09: o mecânico, pelo celular, adiciona a peça: foto, nome, descrição, quantidade.
 *   29/09: "a visualização que eu quero é por cards, em fileiras horizontais de
 *          categorias" — pneus numa, motores noutra… vestuário na última. Dentro de cada
 *          fileira, as subcategorias (marca e medida do pneu, família do motor). A peça
 *          pode ser assinalada para um cliente, e tem valor de compra, margem (campo livre:
 *          15% ou um valor fixo) e o preço final que vai para a invoice.
 *
 * "Contar prateleira" virou "Adicionar peça" (29/09). Informar quanto tem de uma peça que
 * já existe é tocar no card: a primeira coisa da ficha é "Quanto tem agora".
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { api, ApiError } from '../api/client'
import { useGet } from '../api/hooks'
import type { Client } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { Banner, Chip, Empty, ErrorState, Loading, PageHeader, Scrim } from '../components/ui'
import { FotoPeca } from '../components/FotoPeca'
import { Icon } from '../components/Icon'
import { usePerguntar } from '../components/Perguntar'
import { useToast } from '../components/Toast'
import { Picker } from '../components/Unir'

interface Dono { client_id: number; cliente: string; qty: number }
interface ItemEstoque {
  id: number; name: string; kind: string; tracking: string; unit: string
  min_qty: number | null; sku: string | null; supplier_url: string | null
  notes: string | null; tem_foto: boolean
  total: number; nosso: number; de_clientes: number; abaixo: boolean
  contado: boolean; ultima_contagem: string | null
  category: string; prateleira_sugerida: boolean; subcategory: string | null; size: string | null
  price: number | null; cost?: number | null; markup?: string | null
  clientes: Dono[]
}
interface Prateleira { code: string; nome: string; kind: string; unit: string; subcategorias: string[]; medidas: string[]; dica: string }
interface Repor { id: number; name: string; unit: string; falta: number; sku: string | null; supplier_url: string | null }
interface Local { id: number; code: string; name: string }
interface Lista { itens: ItemEstoque[]; prateleiras: Prateleira[]; gerente: boolean; locais: Local[]; repor: Repor[]; divergencias: unknown[]; a_contar: number[] }
interface Movimento { id: number; kind: string; qty: number; qty_before: number | null; qty_after: number | null
  reason: string | null; notes: string | null; at: string; quem: string | null; de_nome: string | null; para_nome: string | null }
interface Saldo { local: string; local_code: string; qty: number; client_id: number | null; cliente: string | null }
interface Unidade { id: number; serial: string; status: string; local: string | null; local_code: string | null; client_id: number | null; cliente: string | null }
interface Ficha { item: ItemEstoque & { supplier: string | null; image_path: string | null }; total: number; nosso: number
  saldos: Saldo[]; unidades: Unidade[]; movimentos: Movimento[] }
interface Cobranca { id: number; item_id: number; name: string; qty: number; unit_price: number | null; total: number | null; created_at: string; por: string | null; notes: string | null }
interface Sugestao { sku: string; name: string; url: string | null; price: number | null; brand: string | null; score: number }

const MOV_ROTULO: Record<string, string> = { entrada: 'entrada', saida: 'saída', ajuste: 'ajuste', transferencia: 'transferência', contagem: 'contagem' }
const EM_CASA = ['disponivel', 'em_uso', 'em_servico', 'emprestado']

function quando(iso: string | null) {
  if (!iso) return '—'
  return `${iso.slice(8, 10)}/${iso.slice(5, 7)} ${iso.slice(11, 16)}`
}
const usd = (v: number | null | undefined) => v === null || v === undefined ? '—' : `$${v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
const num = (s: string) => s.trim() === '' ? null : Number(s.replace(',', '.'))

/** Espelho de `prateleiras.preco_final` — só para a prévia; quem decide é o servidor.
 *  "15%" é porcentagem, "20" é valor fixo em dólar, "15% + 10" soma os dois. */
function precoFinal(custo: number | null, margem: string): number | null | 'erro' {
  if (custo === null || Number.isNaN(custo)) return null
  const t = margem.trim().replace(/^\+/, '')
  if (!t) return null
  let v = custo
  for (const bruto of t.split(/\s*\+\s*/)) {
    const m = bruto.replace(/US\$|\$|\s/g, '').replace(',', '.').match(/^(\d+(?:\.\d+)?)(%?)$/)
    if (!m) return 'erro'
    v = m[2] ? v * (1 + Number(m[1]) / 100) : v + Number(m[1])
  }
  return Math.round(v * 100) / 100
}

/** Valor de compra, margem e preço final — só aparece para gerente. */
/** Valor de compra, margem e preço final — só aparece para gerente.
 *  A margem tem uma chave: % (porcentagem sobre a compra) ou $ (valor fixo somado). O
 *  servidor recebe "15%" ou "20", o mesmo formato de antes. */
function CamposPreco({ custo, setCusto, margem, setMargem, preco, setPreco }: {
  custo: string; setCusto: (v: string) => void; margem: string; setMargem: (v: string) => void; preco: string; setPreco: (v: string) => void
}) {
  const [tipo, setTipo] = useState<'pct' | 'fixo'>(margem.trim() && !margem.includes('%') ? 'fixo' : 'pct')
  const valor = margem.replace(/[%$\s]/g, '').replace(/^\+/, '')
  const montar = (v: string, t: 'pct' | 'fixo') => setMargem(v.trim() ? (t === 'pct' ? `${v.trim()}%` : v.trim()) : '')
  const calc = precoFinal(num(custo), margem)
  const manual = preco.trim() !== ''
  return <>
    <div className="row gap wrap">
      <label className="fld grow"><span>Valor de compra</span>
        <input type="number" inputMode="decimal" min={0} value={custo} onChange={e => setCusto(e.target.value)} placeholder="$ que a URACE paga" /></label>
      <div className="fld grow"><span>Margem</span>
        <div className="margem">
          <input type="number" inputMode="decimal" min={0} value={valor} aria-label="margem"
                 onChange={e => montar(e.target.value, tipo)} placeholder={tipo === 'pct' ? '15' : '20'} />
          <div className="switch" role="radiogroup" aria-label="tipo de margem">
            <button type="button" role="radio" aria-checked={tipo === 'pct'} className={tipo === 'pct' ? 'on' : ''}
                    title="porcentagem sobre o valor de compra" onClick={() => { setTipo('pct'); montar(valor, 'pct') }}>%</button>
            <button type="button" role="radio" aria-checked={tipo === 'fixo'} className={tipo === 'fixo' ? 'on' : ''}
                    title="valor fixo em dólar somado ao valor de compra" onClick={() => { setTipo('fixo'); montar(valor, 'fixo') }}>$</button>
          </div>
        </div></div>
      <label className="fld grow"><span>Preço final ao cliente</span>
        <input type="number" inputMode="decimal" min={0} value={preco} onChange={e => setPreco(e.target.value)}
               placeholder={typeof calc === 'number' ? calc.toFixed(2) : 'calculado'} /></label>
    </div>
    <div className="preco-previa">
      {calc === 'erro' ? <span style={{ color: 'var(--crit)' }}>Margem inválida.</span>
        : manual ? <>Vai para a invoice: <b>{usd(num(preco))}</b> <span className="muted">(digitado)</span></>
        : typeof calc === 'number' ? <>Vai para a invoice: <b>{usd(calc)}</b> <span className="muted">= {usd(num(custo))} + {tipo === 'pct' ? `${valor}%` : usd(num(valor))}</span></>
        : <span className="muted">Com valor de compra e margem, o preço final sai sozinho. Ou digite o preço final direto.</span>}
    </div>
  </>
}

/** De quem é a peça: da URACE ou de um cliente — já na hora de registrar (dono, 29/09). */
function DeQuemE({ deCliente, setDeCliente, cliente, setCliente }: {
  deCliente: boolean; setDeCliente: (v: boolean) => void; cliente: Client | null; setCliente: (c: Client | null) => void
}) {
  return <>
    <div className="fld"><span>De quem é</span>
      <div className="seg">
        <button type="button" className={`btn sm${deCliente ? ' ghost' : ''}`} onClick={() => setDeCliente(false)}>Da URACE</button>
        <button type="button" className={`btn sm${deCliente ? '' : ' ghost'}`} onClick={() => setDeCliente(true)}>De um cliente</button>
      </div></div>
    {deCliente && <Picker label="Cliente dono da peça" value={cliente} onPick={setCliente} />}
  </>
}

/** Adicionar peça — o botão do mecânico, no celular. Foto, nome, prateleira, quanto tem, de quem é. */
function Adicionar({ d, inicial, onClose, reload }: { d: Lista; inicial: string | null; onClose: () => void; reload: () => void }) {
  const toast = useToast()
  const [prat, setPrat] = useState(inicial || d.prateleiras[0]?.code || 'outros')
  const p = d.prateleiras.find(x => x.code === prat)
  const serie = p?.kind === 'motor' || p?.kind === 'chassi'
  const [nome, setNome] = useState('')
  const [sub, setSub] = useState('')
  const [medida, setMedida] = useState('')
  const [descricao, setDescricao] = useState('')
  const [qtd, setQtd] = useState('')
  const [seriais, setSeriais] = useState('')
  const [local, setLocal] = useState(d.locais[0]?.code || 'sede')
  const [deCliente, setDeCliente] = useState(false)
  const [cliente, setCliente] = useState<Client | null>(null)
  const [minimo, setMinimo] = useState('')
  const [unidade, setUnidade] = useState('')
  const [custo, setCusto] = useState('')
  const [margem, setMargem] = useState('')
  const [preco, setPreco] = useState('')
  const [foto, setFoto] = useState<File | null>(null)
  const [previa, setPrevia] = useState<string | null>(null)
  const [salvando, setSalvando] = useState(false)

  function escolher(f: File | null) {
    setFoto(f)
    setPrevia(old => { if (old) URL.revokeObjectURL(old); return f ? URL.createObjectURL(f) : null })
  }

  async function salvar() {
    if (!nome.trim()) { toast('A peça precisa de um nome.', 'warn'); return }
    if (deCliente && !cliente) { toast('Escolha o cliente dono da peça.', 'warn'); return }
    if (d.gerente && precoFinal(num(custo), margem) === 'erro') { toast('Não entendi a margem.', 'warn'); return }
    setSalvando(true)
    try {
      const fd = new FormData()
      fd.append('name', nome.trim())
      fd.append('category', prat)
      fd.append('local', local)
      if (sub.trim()) fd.append('subcategory', sub.trim())
      if (medida.trim()) fd.append('size', medida.trim())
      if (descricao.trim()) fd.append('notes', descricao.trim())
      if (unidade.trim()) fd.append('unit', unidade.trim())
      if (serie) { if (seriais.trim()) fd.append('serial', seriais.trim()) }
      else {
        if (qtd.trim()) fd.append('qty', qtd.trim().replace(',', '.'))
        if (minimo.trim()) fd.append('min_qty', minimo.trim().replace(',', '.'))
      }
      if (deCliente && cliente) fd.append('client_id', String(cliente.id))
      if (d.gerente) {
        if (custo.trim()) fd.append('cost', custo.trim())
        if (margem.trim()) fd.append('markup', margem.trim())
        if (preco.trim()) fd.append('price', preco.trim())
      }
      if (foto) fd.append('foto', foto)
      const res = await api.postForm<{ id: number; aviso: string | null }>('/estoque/item', fd)
      toast(res.aviso || `${nome.trim()} adicionada em ${p?.nome || 'estoque'}.`, res.aviso ? 'warn' : 'ok')
      reload(); onClose()
    } catch (e) {
      toast((e as ApiError).message, 'crit')
    } finally { setSalvando(false) }
  }

  return <Scrim onMouseDown={onClose}><div className="modal" style={{ maxWidth: 560 }} onMouseDown={e => e.stopPropagation()}>
    <h3>Adicionar peça</h3>
    <FotoPeca previa={previa} onFile={escolher} />

    <label className="fld"><span>Nome da peça</span>
      <input value={nome} onChange={e => setNome(e.target.value)} placeholder={prat === 'pneus' ? 'MG SH2 Red' : 'Pastilha de freio Tonykart'} /></label>

    <label className="fld"><span>Prateleira</span>
      <select value={prat} onChange={e => { setPrat(e.target.value); setSub(''); setMedida('') }}>
        {d.prateleiras.map(x => <option key={x.code} value={x.code}>{x.nome}</option>)}
      </select></label>

    <div className="row gap wrap">
      <label className="fld grow"><span>{prat === 'pneus' || prat === 'motores' || prat === 'chassis' ? 'Marca' : 'Tipo'}</span>
        <input list={`sub-${prat}`} value={sub} onChange={e => setSub(e.target.value)} placeholder={p?.subcategorias[0] || ''} />
        <datalist id={`sub-${prat}`}>{p?.subcategorias.map(s => <option key={s} value={s} />)}</datalist></label>
      <label className="fld grow"><span>{prat === 'vestuario' ? 'Tamanho' : 'Medida'}</span>
        <input list={`med-${prat}`} value={medida} onChange={e => setMedida(e.target.value)} placeholder={p?.medidas[0] || ''} />
        <datalist id={`med-${prat}`}>{p?.medidas.map(s => <option key={s} value={s} />)}</datalist></label>
    </div>
    {p?.dica && <p className="small muted" style={{ marginTop: -4 }}>{p.dica}</p>}

    {serie
      ? <label className="fld"><span>Número de série <i className="muted">(um por linha — cada motor/chassi é uma ficha)</i></span>
        <textarea rows={2} value={seriais} onChange={e => setSeriais(e.target.value)} placeholder="X30-123456" /></label>
      : <div className="row gap wrap">
        <label className="fld grow"><span>Quantidade que tem agora</span>
          <input type="number" inputMode="decimal" min={0} value={qtd} onChange={e => setQtd(e.target.value)} placeholder={p?.unit || 'un'} /></label>
        {d.locais.length > 1 && <label className="fld grow"><span>Onde</span>
          <select value={local} onChange={e => setLocal(e.target.value)}>{d.locais.map(l => <option key={l.code} value={l.code}>{l.name}</option>)}</select></label>}
      </div>}
    {serie && d.locais.length > 1 && <label className="fld"><span>Onde</span>
      <select value={local} onChange={e => setLocal(e.target.value)}>{d.locais.map(l => <option key={l.code} value={l.code}>{l.name}</option>)}</select></label>}

    <DeQuemE deCliente={deCliente} setDeCliente={setDeCliente} cliente={cliente} setCliente={setCliente} />

    <label className="fld"><span>Descrição <i className="muted">(onde fica, para que serve)</i></span>
      <textarea value={descricao} onChange={e => setDescricao(e.target.value)} rows={2} /></label>

    {d.gerente && <CamposPreco custo={custo} setCusto={setCusto} margem={margem} setMargem={setMargem} preco={preco} setPreco={setPreco} />}

    <details className="small" style={{ margin: '8px 0' }}><summary style={{ cursor: 'pointer' }}>Mais: mínimo e unidade</summary>
      <div className="row gap wrap">
        {!serie && <label className="fld grow"><span>Avisar quando faltar <i className="muted">(mínimo)</i></span>
          <input type="number" inputMode="decimal" value={minimo} onChange={e => setMinimo(e.target.value)} placeholder="4" /></label>}
        <label className="fld grow"><span>Unidade</span>
          <input value={unidade} onChange={e => setUnidade(e.target.value)} placeholder={p?.unit || 'un'} /></label>
      </div></details>

    <div className="modal-foot">
      <button className="btn ghost" onClick={onClose}>Cancelar</button>
      <button className="btn" disabled={salvando || !nome.trim()} onClick={salvar}>{salvando ? 'Salvando…' : 'Adicionar peça'}</button>
    </div>
  </div></Scrim>
}

/** Mexer numa peça: quanto tem agora, usei, chegou, levei para o trailer. */
function Mover({ ficha, locais, onDone }: { ficha: Ficha; locais: Local[]; onDone: () => void }) {
  const toast = useToast()
  const [tipo, setTipo] = useState<'contar' | 'entrada' | 'saida' | 'transferir'>('contar')
  const [qtd, setQtd] = useState('')
  const [de, setDe] = useState(locais[0]?.code || 'sede')
  const [para, setPara] = useState(locais[1]?.code || 'trailer')
  const [nota, setNota] = useState('')
  const [deCliente, setDeCliente] = useState(false)
  const [cliente, setCliente] = useState<Client | null>(null)
  const [usadaEm, setUsadaEm] = useState<Client | null>(null)
  const [indo, setIndo] = useState(false)
  if (ficha.item.tracking !== 'quantidade') return <p className="small muted">Motor e chassi andam por unidade (número de série).
    Para cadastrar mais uma unidade, use <b>Adicionar peça</b> com o número de série.</p>

  async function enviar() {
    const q = num(qtd)
    if (q === null || Number.isNaN(q) || q < 0 || (q === 0 && tipo !== 'contar')) { toast('Informe a quantidade.', 'warn'); return }
    if (deCliente && !cliente) { toast('Escolha o cliente dono da peça.', 'warn'); return }
    const dono = deCliente && cliente ? cliente.id : null
    // peça da URACE usada no kart de um cliente: vai para a cobrança dele (29/09)
    const paraQuem = tipo === 'saida' ? (dono ?? usadaEm?.id ?? null) : null
    setIndo(true)
    try {
      if (tipo === 'contar') {
        const r = await api.post<{ antes: number; depois: number }>('/estoque/contar', { item_id: ficha.item.id, qty: q, local: de, client_id: dono, nota: nota.trim() || null })
        toast(r.antes === r.depois ? `Conferido: ${r.depois} ${ficha.item.unit}.` : `Agora são ${r.depois} ${ficha.item.unit} (eram ${r.antes}).`, 'ok')
      } else {
        const r = await api.post<{ cobranca_id?: number }>(`/estoque/${tipo}`, { item_id: ficha.item.id, qty: q, local: de, para, nota: nota.trim() || null,
                                             client_id: dono, para_cliente_id: paraQuem,
                                             motivo: tipo === 'entrada' ? (dono ? 'recebido do cliente' : 'compra') : tipo === 'saida' ? 'uso em serviço' : null })
        toast(tipo === 'entrada' ? 'Entrada registrada.' : tipo === 'transferir' ? 'Transferência registrada.'
          : r.cobranca_id ? `Saída registrada — ficou a cobrar de ${usadaEm?.pilot_name || usadaEm?.name}${ficha.item.price != null ? ` ($${(ficha.item.price * q).toFixed(2)})` : ' (sem preço final: o gerente define)'}.` : 'Saída registrada.', 'ok')
        setUsadaEm(null)
      }
      setQtd(''); setNota(''); onDone()
    } catch (e) {
      toast((e as ApiError).message, 'crit')
    } finally { setIndo(false) }
  }

  const ROT = { contar: 'Quanto tem agora', saida: 'Usei em serviço', entrada: 'Chegou', transferir: 'Levar para outro local' }
  return <div>
    <div className="seg">
      {(['contar', 'saida', 'entrada', 'transferir'] as const).map(t => <button key={t} className={`btn sm${tipo === t ? '' : ' ghost'}`} onClick={() => setTipo(t)}>{ROT[t]}</button>)}
    </div>
    {tipo === 'contar' && <p className="small muted">O número que você contou na prateleira vira o saldo; a diferença fica no histórico.</p>}
    <div className="row gap wrap">
      <label className="fld grow"><span>Quantidade</span>
        <input type="number" inputMode="decimal" min={0} value={qtd} onChange={e => setQtd(e.target.value)} placeholder={ficha.item.unit} autoFocus /></label>
      {locais.length > 1 && <label className="fld grow"><span>{tipo === 'entrada' ? 'Para' : tipo === 'contar' ? 'Onde' : 'De'}</span>
        <select value={de} onChange={e => setDe(e.target.value)}>{locais.map(l => <option key={l.code} value={l.code}>{l.name}</option>)}</select></label>}
      {tipo === 'transferir' && <label className="fld grow"><span>Para</span>
        <select value={para} onChange={e => setPara(e.target.value)}>{locais.map(l => <option key={l.code} value={l.code}>{l.name}</option>)}</select></label>}
    </div>
    <DeQuemE deCliente={deCliente} setDeCliente={setDeCliente} cliente={cliente} setCliente={setCliente} />
    {tipo === 'saida' && !deCliente && <>
      <Picker label="Usada no kart de (opcional — vai para a cobrança do cliente)" value={usadaEm} onPick={setUsadaEm} />
      {usadaEm && <p className="small muted" style={{ marginTop: -4 }}>{ficha.item.price != null
        ? <>Fica a cobrar de {usadaEm.pilot_name || usadaEm.name}: {qtd || '?'} × ${ficha.item.price.toFixed(2)}. Entra na próxima invoice dele.</>
        : <>Esta peça ainda não tem preço final: a cobrança fica registrada e o gerente põe o valor.</>}</p>}
    </>}
    <label className="fld"><span>Nota <i className="muted">(qual kart, nota fiscal)</i></span>
      <input value={nota} onChange={e => setNota(e.target.value)} /></label>
    <button className="btn" disabled={indo || !qtd} onClick={enviar}>{indo ? 'Registrando…' : 'Registrar'}</button>
  </div>
}

/** De quem é: assinalar para um cliente (mecânico) e devolver para a URACE (gerente). */
function DonoDaPeca({ ficha, locais, gerente, onDone }: { ficha: Ficha; locais: Local[]; gerente: boolean; onDone: () => void }) {
  const toast = useToast()
  const serie = ficha.item.tracking === 'serie'
  const [cliente, setCliente] = useState<Client | null>(null)
  const [qtd, setQtd] = useState('')
  const [local, setLocal] = useState(locais[0]?.code || 'sede')
  const [unidade, setUnidade] = useState<number | null>(null)
  const [indo, setIndo] = useState(false)
  const nossas = ficha.unidades.filter(u => !u.client_id && EM_CASA.includes(u.status))
  const nossoAqui = ficha.saldos.filter(s => !s.client_id && s.local_code === local).reduce((a, s) => a + s.qty, 0)
  const deClientes = [...ficha.saldos.filter(s => s.client_id && s.qty > 0).map(s => ({ chave: `l${s.client_id}${s.local_code}`, client_id: s.client_id!, cliente: s.cliente, qty: s.qty, local: s.local, local_code: s.local_code, unit_id: null as number | null })),
                      ...ficha.unidades.filter(u => u.client_id && EM_CASA.includes(u.status)).map(u => ({ chave: `u${u.id}`, client_id: u.client_id!, cliente: u.cliente, qty: 1, local: u.local || '', local_code: u.local_code || 'sede', unit_id: u.id as number | null, serial: u.serial }))]

  async function assinalar() {
    if (!cliente) { toast('Escolha o cliente.', 'warn'); return }
    const q = num(qtd)
    if (!serie && (!q || q <= 0)) { toast('Informe quantos são dele.', 'warn'); return }
    if (serie && !unidade) { toast('Escolha qual unidade.', 'warn'); return }
    setIndo(true)
    try {
      await api.post('/estoque/assinalar', { item_id: ficha.item.id, client_id: cliente.id, qty: serie ? null : q, unit_id: serie ? unidade : null, local })
      toast(`Assinalado para ${cliente.pilot_name || cliente.name}.`, 'ok')
      setCliente(null); setQtd(''); setUnidade(null); onDone()
    } catch (e) { toast((e as ApiError).message, 'crit') } finally { setIndo(false) }
  }
  async function devolver(x: typeof deClientes[number]) {
    setIndo(true)
    try {
      await api.post('/estoque/devolver', { item_id: ficha.item.id, client_id: x.client_id, qty: x.unit_id ? null : x.qty, unit_id: x.unit_id, local: x.local_code })
      toast('Voltou a ser da URACE.', 'ok'); onDone()
    } catch (e) { toast((e as ApiError).message, 'crit') } finally { setIndo(false) }
  }

  return <div>
    {deClientes.length
      ? <div className="tbl" style={{ marginBottom: 10 }}>{deClientes.map(x => <div className="tr" key={x.chave}>
        <div className="grow"><b>{x.cliente}</b><div className="small muted">{'serial' in x ? `série ${x.serial} · ` : `${x.qty} ${ficha.item.unit} · `}{x.local}</div></div>
        {gerente && <button className="btn ghost sm" disabled={indo} onClick={() => devolver(x)} title="assinalado por engano, ou o cliente vendeu para a URACE">devolver p/ URACE</button>}
      </div>)}</div>
      : <p className="small muted">Nenhuma unidade desta peça é de cliente.</p>}
    <h4 style={{ margin: '6px 0' }}>Assinalar para um cliente</h4>
    <p className="small muted">A peça continua na prateleira; passa a ser do cliente e nunca sai para outro.</p>
    <Picker label="Cliente" value={cliente} onPick={setCliente} />
    {serie
      ? <label className="fld"><span>Qual unidade</span>
        <select value={unidade ?? ''} onChange={e => setUnidade(e.target.value ? Number(e.target.value) : null)}>
          <option value="">—</option>{nossas.map(u => <option key={u.id} value={u.id}>série {u.serial}{u.local ? ` · ${u.local}` : ''}</option>)}
        </select></label>
      : <div className="row gap wrap">
        <label className="fld grow"><span>Quantos são dele <i className="muted">(da URACE aqui: {nossoAqui})</i></span>
          <input type="number" inputMode="decimal" min={0} value={qtd} onChange={e => setQtd(e.target.value)} placeholder={ficha.item.unit} /></label>
        {locais.length > 1 && <label className="fld grow"><span>Onde</span>
          <select value={local} onChange={e => setLocal(e.target.value)}>{locais.map(l => <option key={l.code} value={l.code}>{l.name}</option>)}</select></label>}
      </div>}
    <button className="btn" disabled={indo || !cliente} onClick={assinalar}>{indo ? 'Salvando…' : 'Assinalar'}</button>
  </div>
}

/** Editar a ficha: o mecânico mexe em nome, prateleira e medida; o gerente, no preço. */
function Editar({ ficha, d, onDone }: { ficha: Ficha; d: Lista; onDone: () => void }) {
  const toast = useToast()
  const it = ficha.item
  const [nome, setNome] = useState(it.name)
  const [prat, setPrat] = useState(it.category)
  const [sub, setSub] = useState(it.subcategory || '')
  const [medida, setMedida] = useState(it.size || '')
  const [notas, setNotas] = useState(it.notes || '')
  const [minimo, setMinimo] = useState(it.min_qty === null ? '' : String(it.min_qty))
  const [custo, setCusto] = useState(it.cost === null || it.cost === undefined ? '' : String(it.cost))
  const [margem, setMargem] = useState(it.markup || '')
  const [preco, setPreco] = useState(it.price === null ? '' : String(it.price))
  const [indo, setIndo] = useState(false)
  const p = d.prateleiras.find(x => x.code === prat)
  const precoCalculado = !it.markup || it.cost === null || it.cost === undefined ? null : precoFinal(it.cost, it.markup)

  async function salvar() {
    const corpo: Record<string, unknown> = { name: nome.trim(), category: prat, subcategory: sub.trim() || null, size: medida.trim() || null,
                                             notes: notas.trim() || null }
    if (it.tracking === 'quantidade') corpo.min_qty = num(minimo)
    if (d.gerente) {
      if (precoFinal(num(custo), margem) === 'erro') { toast('Não entendi a margem.', 'warn'); return }
      corpo.cost = num(custo); corpo.markup = margem.trim() || null
      // preço que só repete a conta vai vazio: assim, mudar custo ou margem refaz o preço final
      const pv = num(preco)
      corpo.price = pv !== null && typeof precoCalculado === 'number' && Math.abs(pv - precoCalculado) < 0.005 ? null : pv
    }
    setIndo(true)
    try {
      await api.patch(`/estoque/item/${it.id}`, corpo)
      toast('Ficha salva.', 'ok'); onDone()
    } catch (e) { toast((e as ApiError).message, 'crit') } finally { setIndo(false) }
  }

  return <div>
    <label className="fld"><span>Nome</span><input value={nome} onChange={e => setNome(e.target.value)} /></label>
    <label className="fld"><span>Prateleira{it.prateleira_sugerida && <i className="muted"> (sugerida pelo nome — confirme)</i>}</span>
      <select value={prat} onChange={e => setPrat(e.target.value)}>{d.prateleiras.map(x => <option key={x.code} value={x.code}>{x.nome}</option>)}</select></label>
    <div className="row gap wrap">
      <label className="fld grow"><span>{prat === 'pneus' || prat === 'motores' || prat === 'chassis' ? 'Marca' : 'Tipo'}</span>
        <input list={`esub-${prat}`} value={sub} onChange={e => setSub(e.target.value)} />
        <datalist id={`esub-${prat}`}>{p?.subcategorias.map(s => <option key={s} value={s} />)}</datalist></label>
      <label className="fld grow"><span>{prat === 'vestuario' ? 'Tamanho' : 'Medida'}</span>
        <input list={`emed-${prat}`} value={medida} onChange={e => setMedida(e.target.value)} />
        <datalist id={`emed-${prat}`}>{p?.medidas.map(s => <option key={s} value={s} />)}</datalist></label>
      {it.tracking === 'quantidade' && <label className="fld grow"><span>Mínimo</span>
        <input type="number" inputMode="decimal" value={minimo} onChange={e => setMinimo(e.target.value)} /></label>}
    </div>
    <label className="fld"><span>Descrição</span><textarea rows={2} value={notas} onChange={e => setNotas(e.target.value)} /></label>
    {d.gerente && <CamposPreco custo={custo} setCusto={setCusto} margem={margem} setMargem={setMargem} preco={preco} setPreco={setPreco} />}
    <button className="btn" disabled={indo || !nome.trim()} onClick={salvar} style={{ marginTop: 10 }}>{indo ? 'Salvando…' : 'Salvar ficha'}</button>
  </div>
}

/** Ligar a peça ao catálogo da Comet (gerente). O dono deixou o SKU para depois (29/09). */
function LigarSku({ ficha, onDone }: { ficha: Ficha; onDone: () => void }) {
  const toast = useToast()
  const sug = useGet<{ tem_catalogo: boolean; sugestoes: Sugestao[] }>(`/estoque/item/${ficha.item.id}/sku-sugestoes`)
  const [indo, setIndo] = useState<string | null>(null)
  async function ligar(sku: string) {
    setIndo(sku)
    try { await api.post(`/estoque/item/${ficha.item.id}/sku`, { sku }); toast(`Ligada ao SKU ${sku}.`, 'ok'); onDone() }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setIndo(null) }
  }
  if (sug.loading && !sug.data) return <Loading rows={2} />
  if (sug.error) return <ErrorState error={sug.error} retry={sug.reload} />
  if (!sug.data?.tem_catalogo) return <p className="small muted">O catálogo do fornecedor ainda não foi importado neste painel.</p>
  if (!sug.data.sugestoes.length) return <p className="small muted">Nenhum produto do catálogo parece com o nome desta peça.</p>
  return <div className="tbl">
    {sug.data.sugestoes.map(x => <div className="tr" key={x.sku}>
      <div className="grow"><b>{x.name}</b>
        <div className="small muted">SKU {x.sku}{x.brand ? ` · ${x.brand}` : ''}{x.price ? ` · $${x.price.toFixed(2)}` : ''}</div></div>
      {x.url && <a className="btn ghost sm" href={x.url} target="_blank" rel="noreferrer">ver</a>}
      {ficha.item.sku === x.sku ? <Chip tone="ok">ligada</Chip>
        : <button className="btn sm" disabled={!!indo} onClick={() => ligar(x.sku)}>{indo === x.sku ? '…' : 'É este'}</button>}
    </div>)}
  </div>
}

function FichaPeca({ id, d, onClose, reload }: { id: number; d: Lista; onClose: () => void; reload: () => void }) {
  const toast = useToast()
  const f = useGet<Ficha>(`/estoque/${id}`)
  const [aba, setAba] = useState<'mover' | 'dono' | 'editar' | 'historico' | 'sku'>('mover')
  const [versao, setVersao] = useState(0)
  const recarregar = () => { f.reload(); reload(); setVersao(v => v + 1) }
  const it = f.data?.item
  const prat = d.prateleiras.find(x => x.code === it?.category)

  async function trocarFoto(file: File | null) {
    if (!file || !it) return
    const fd = new FormData(); fd.append('foto', file)
    try { await api.postForm(`/estoque/item/${it.id}/foto`, fd); toast('Foto trocada.', 'ok'); recarregar() }
    catch (e) { toast((e as ApiError).message, 'crit') }
  }

  const ABAS = { mover: 'Quantidade', dono: 'Cliente', editar: 'Editar', historico: 'Histórico', sku: 'SKU' } as const
  return <Scrim onMouseDown={onClose}><div className="modal" style={{ maxWidth: 620 }} onMouseDown={e => e.stopPropagation()}>
    {f.error && <ErrorState error={f.error} retry={f.reload} />}
    {f.loading && !f.data && <Loading />}
    {f.data && it && <>
      <FotoPeca previa={it.image_path ? `/ops/api/estoque/item/${it.id}/foto?v=${versao}` : null} onFile={trocarFoto} rotulo="Adicionar imagem" />
      <h3 style={{ marginTop: 10 }}>{it.name}</h3>
      <p className="small muted">{prat?.nome || it.category}{it.subcategory ? ` · ${it.subcategory}` : ''}{it.size ? ` · ${it.size}` : ''}
        {it.min_qty ? ` · mínimo ${it.min_qty} ${it.unit}` : ''}</p>
      <div className="row gap wrap">
        <Chip tone={it.tracking === 'quantidade' && !f.data.movimentos.length ? 'neutral' : 'ok'}>da URACE: {f.data.nosso} {it.unit}</Chip>
        {f.data.total !== f.data.nosso && <Chip tone="info">de clientes: {f.data.total - f.data.nosso}</Chip>}
        {it.price !== null && <Chip tone="accent">preço final {usd(it.price)}</Chip>}
        {d.gerente && it.cost !== null && it.cost !== undefined && <Chip tone="outline">compra {usd(it.cost)}{it.markup ? ` · margem ${it.markup}` : ''}</Chip>}
      </div>
      <div className="seg" style={{ margin: '12px 0' }}>
        {(Object.keys(ABAS) as (keyof typeof ABAS)[]).filter(k => k !== 'sku' || d.gerente).map(k =>
          <button key={k} className={`btn sm${aba === k ? '' : ' ghost'}`} onClick={() => setAba(k)}>{ABAS[k]}</button>)}
      </div>
      {aba === 'mover' && <Mover ficha={f.data} locais={d.locais} onDone={recarregar} />}
      {aba === 'dono' && <DonoDaPeca ficha={f.data} locais={d.locais} gerente={d.gerente} onDone={recarregar} />}
      {aba === 'editar' && <Editar ficha={f.data} d={d} onDone={recarregar} />}
      {aba === 'historico' && (f.data.movimentos.length
        ? <div className="tbl" style={{ maxHeight: '40vh', overflow: 'auto' }}>
          {f.data.movimentos.map(m => <div className="tr" key={m.id}>
            <div className="grow"><b>{MOV_ROTULO[m.kind] || m.kind}</b> {m.qty} {it.unit}
              {m.para_nome && m.de_nome && m.para_nome !== m.de_nome ? ` · ${m.de_nome} → ${m.para_nome}` : m.para_nome ? ` · ${m.para_nome}` : m.de_nome ? ` · ${m.de_nome}` : ''}
              <div className="small muted">{quando(m.at)} · {m.quem || 'sistema'}{m.reason ? ` · ${m.reason}` : ''}{m.notes ? ` · ${m.notes}` : ''}</div></div>
            {m.qty_before !== null && m.qty_after !== null && <span className="small muted">{m.qty_before} → {m.qty_after}</span>}
          </div>)}
        </div>
        : <Empty title="Sem histórico">Ninguém informou a quantidade desta peça ainda: o zero dela é "ninguém contou", não "acabou".</Empty>)}
      {aba === 'sku' && <LigarSku ficha={f.data} onDone={recarregar} />}
      <div className="modal-foot"><button className="btn ghost" onClick={onClose}>Fechar</button></div>
    </>}
  </div></Scrim>
}

/** Um card da prateleira: foto, nome, marca/medida, quanto tem, de quem é, preço. */
function CardPeca({ i, gerente, onOpen, onExcluir }: { i: ItemEstoque; gerente: boolean; onOpen: () => void; onExcluir?: () => void }) {
  const semQtd = i.tracking === 'quantidade' && !i.contado
  const card = <button className="pcard" onClick={onOpen}>
    <div className="ph">{i.tem_foto ? <img src={`/ops/api/estoque/item/${i.id}/foto`} alt="" loading="lazy" draggable={false} /> : <Icon name="box" size={28} />}</div>
    <div className="bd">
      <div className="nm">{i.name}</div>
      <div className="sb">{[i.subcategory, i.size].filter(Boolean).join(' · ') || ' '}</div>
      {semQtd ? <div className="qt"><small style={{ marginLeft: 0 }}>sem quantidade</small></div>
        : <div className={`qt${i.abaixo ? ' warn' : ''}`}>{i.nosso}<small>{i.unit}</small></div>}
      <div className="ft">
        {i.clientes.slice(0, 2).map(c => <Chip key={c.client_id} tone="info" title="peça de cliente guardada com a gente">{c.qty} · {c.cliente}</Chip>)}
        {i.clientes.length > 2 && <Chip tone="info">+{i.clientes.length - 2}</Chip>}
        {i.abaixo && !semQtd && <Chip tone="warn">repor</Chip>}
        {i.price !== null ? <Chip tone="accent">{usd(i.price)}</Chip> : gerente && <Chip tone="outline">sem preço</Chip>}
      </div>
    </div>
  </button>
  if (!onExcluir) return card
  // A lixeira fica por cima da foto, fora do botão do card (botão dentro de botão não vale)
  return <div className="pcard-w">{card}
    <button className="pcard-lixo" aria-label={`Excluir ${i.name}`} title="Excluir peça" onClick={onExcluir}><Icon name="trash" size={18} /></button>
  </div>
}

/** Clicar, segurar e arrastar a fileira para o lado — sem barra de rolagem (dono, 29/09).
 *  Só para mouse: no celular o dedo já rola nativo. Se arrastou, o clique que termina o
 *  gesto não abre o card. */
function useArrastar() {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    let x0 = 0, s0 = 0, ativo = false, moveu = false
    const down = (e: PointerEvent) => {
      if (e.pointerType !== 'mouse' || e.button !== 0) return
      ativo = true; moveu = false; x0 = e.clientX; s0 = el.scrollLeft
    }
    const move = (e: PointerEvent) => {
      if (!ativo) return
      const dx = e.clientX - x0
      if (!moveu && Math.abs(dx) > 5) { moveu = true; el.classList.add('arrastando'); el.setPointerCapture(e.pointerId) }
      if (moveu) el.scrollLeft = s0 - dx
    }
    const up = (e: PointerEvent) => {
      if (!ativo) return
      ativo = false; el.classList.remove('arrastando')
      if (el.hasPointerCapture(e.pointerId)) el.releasePointerCapture(e.pointerId)
    }
    const click = (e: MouseEvent) => { if (moveu) { e.preventDefault(); e.stopPropagation(); moveu = false } }
    el.addEventListener('pointerdown', down); el.addEventListener('pointermove', move)
    el.addEventListener('pointerup', up); el.addEventListener('pointercancel', up)
    el.addEventListener('click', click, true)
    return () => {
      el.removeEventListener('pointerdown', down); el.removeEventListener('pointermove', move)
      el.removeEventListener('pointerup', up); el.removeEventListener('pointercancel', up)
      el.removeEventListener('click', click, true)
    }
  }, [])
  return ref
}

/** Uma fileira: a prateleira, com as marcas/tipos como filtro. */
function Fileira({ p, itens, gerente, onOpen, onAdd, podeAdd, onExcluir }: { p: Prateleira; itens: ItemEstoque[]; gerente: boolean; onOpen: (id: number) => void; onAdd: () => void; podeAdd: boolean; onExcluir?: (i: ItemEstoque) => void }) {
  const [filtro, setFiltro] = useState<string | null>(null)
  const arrasto = useArrastar()
  const subs = useMemo(() => [...new Set(itens.map(i => i.subcategory).filter(Boolean) as string[])].sort(), [itens])
  const vis = filtro ? itens.filter(i => i.subcategory === filtro) : itens
  return <div className="shelf">
    <div className="shelf-h">
      <h2>{p.nome}</h2><span className="small muted">{itens.length}</span>
      {subs.length > 1 && <div className="chips">
        <button className={`btn sm${filtro ? ' ghost' : ''}`} onClick={() => setFiltro(null)}>todas</button>
        {subs.map(s => <button key={s} className={`btn sm${filtro === s ? '' : ' ghost'}`} onClick={() => setFiltro(filtro === s ? null : s)}>{s}</button>)}
      </div>}
    </div>
    <div className="shelf-row" ref={arrasto}>
      {vis.map(i => <CardPeca key={i.id} i={i} gerente={gerente} onOpen={() => onOpen(i.id)} onExcluir={onExcluir && (() => onExcluir(i))} />)}
      {podeAdd && <button className="pcard novo" onClick={onAdd}><Icon name="plus" size={22} />Adicionar em {p.nome}</button>}
    </div>
  </div>
}

export function Estoque() {
  const { can } = useAuth()
  const lista = useGet<Lista>('/estoque')
  const [abrir, setAbrir] = useState<string | null | false>(false)
  const [ficha, setFicha] = useState<number | null>(null)
  const [busca, setBusca] = useState('')
  const [vazias, setVazias] = useState(false)
  const perguntar = usePerguntar()
  const toast = useToast()
  const d = lista.data

  // Dono, 06/10: lixeira no card, "deseja realmente excluir essa peça?", sim ou não.
  async function excluir(i: ItemEstoque) {
    if (!await perguntar({ titulo: 'Deseja realmente excluir esta peça?', texto: <><b>{i.name}</b> sai das prateleiras. O histórico dela fica guardado.</>,
      ok: 'Sim, excluir', cancelar: 'Não', perigo: true })) return
    try {
      await api.del(`/estoque/item/${i.id}`)
      toast(`${i.name} excluída.`, 'ok')
      lista.reload()
    } catch (e) { toast(e instanceof ApiError ? e.message : 'Não deu para excluir.', 'crit') }
  }

  const itens = useMemo(() => {
    const t = busca.trim().toLowerCase()
    return (d?.itens || []).filter(i => !t || [i.name, i.sku, i.subcategory, i.size, ...i.clientes.map(c => c.cliente)]
      .some(x => (x || '').toLowerCase().includes(t)))
  }, [d, busca])
  const porPrateleira = useMemo(() => {
    const m: Record<string, ItemEstoque[]> = {}
    for (const i of itens) (m[i.category] ||= []).push(i)
    for (const k of Object.keys(m)) m[k].sort((a, b) => (a.subcategory || '').localeCompare(b.subcategory || '') || a.name.localeCompare(b.name))
    return m
  }, [itens])
  useEffect(() => { if (busca) setVazias(false) }, [busca])

  const deClientes = (d?.itens || []).filter(i => i.de_clientes > 0)
  const semQtd = d?.a_contar.length || 0
  // repor só o que alguém contou: zero de peça sem quantidade informada não é falta (25/09)
  const faltando = (d?.repor || []).filter(r => !d?.a_contar.includes(r.id))

  return <>
    <PageHeader title="Estoque" help="Uma fileira por prateleira. Toque na peça para informar quanto tem, assinalar para um cliente ou editar.">
      {can('OPERATOR') && <button className="btn" onClick={() => setAbrir(null)}><Icon name="plus" size={16} /> Adicionar peça</button>}
    </PageHeader>

    {lista.error && <ErrorState error={lista.error} retry={lista.reload} />}
    {lista.loading && !d && <Loading />}

    {d && <>
      <div className="est-resumo">
        <Chip tone="neutral">{d.itens.length} peças</Chip>
        {!!faltando.length && <Chip tone="warn">{faltando.length} para repor</Chip>}
        {!!semQtd && <Chip tone="warn" title="o zero delas é 'ninguém contou', não 'acabou'">{semQtd} sem quantidade</Chip>}
        {!!deClientes.length && <Chip tone="info">{deClientes.length} com peça de cliente</Chip>}
      </div>

      {!!d.divergencias.length && <Banner tone="crit">
        {d.divergencias.length} saldo(s) não batem com o histórico de movimentos. Alguém mexeu
        no banco por fora, ou há defeito. Vale conferir antes de confiar nos números.</Banner>}

      {!!faltando.length && <details className="card card-b" style={{ margin: '8px 0' }}>
        <summary style={{ cursor: 'pointer' }}><b>Precisa comprar</b> <span className="small muted">· {faltando.length} abaixo do mínimo</span></summary>
        <div className="tbl" style={{ marginTop: 8 }}>
          {faltando.map(r => <div className="tr" key={r.id} role="button" tabIndex={0} style={{ cursor: 'pointer' }} onClick={() => setFicha(r.id)}>
            <div className="grow"><b>{r.name}</b>{r.sku && <span className="small muted"> · SKU {r.sku}</span>}</div>
            <Chip tone="warn">faltam {r.falta} {r.unit}</Chip>
            {r.supplier_url && <a className="btn ghost sm" href={r.supplier_url} target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()}>fornecedor</a>}
          </div>)}
        </div>
      </details>}

      <div className="row gap wrap" style={{ marginTop: 10, alignItems: 'center' }}>
        <input className="inp grow" style={{ flex: '1 1 220px' }} placeholder="Buscar peça, marca, medida ou cliente" value={busca} onChange={e => setBusca(e.target.value)} />
        {!busca && <label className="check small"><input type="checkbox" checked={vazias} onChange={e => setVazias(e.target.checked)} /> mostrar prateleiras vazias</label>}
      </div>

      {!itens.length && busca && <Empty title="Nada com esse nome" />}
      {!d.itens.length && !busca && <Empty title="O estoque está vazio">Use <b>Adicionar peça</b> para cadastrar o que está na prateleira.</Empty>}
      {d.prateleiras.filter(p => (porPrateleira[p.code] || []).length || (vazias && !busca)).map(p =>
        <Fileira key={p.code} p={p} itens={porPrateleira[p.code] || []} gerente={d.gerente} podeAdd={can('OPERATOR')}
                 onOpen={setFicha} onAdd={() => setAbrir(p.code)} onExcluir={can('OPERATOR') ? excluir : undefined} />)}
    </>}

    {abrir !== false && d && <Adicionar d={d} inicial={abrir} onClose={() => setAbrir(false)} reload={lista.reload} />}
    {ficha !== null && d && <FichaPeca id={ficha} d={d} onClose={() => setFicha(null)} reload={lista.reload} />}
  </>
}

/** No card do cliente (29/09): o que é dele e está guardado com a gente, e assinalar mais. */
export function PecasDoCliente({ cid, nome }: { cid: number; nome: string }) {
  const toast = useToast()
  const { can } = useAuth()
  const dele = useGet<{ unidades: (Unidade & { item_id: number; name: string; kind: string })[]; pecas: { id: number; item_id: number; name: string; unit: string; qty: number; local: string; local_code: string; size: string | null; subcategory: string | null }[] }>(`/estoque/cliente/${cid}`)
  const est = useGet<Lista>('/estoque')
  const [item, setItem] = useState<number | ''>('')
  const [qtd, setQtd] = useState('')
  const [local, setLocal] = useState('sede')
  const [unidade, setUnidade] = useState<number | ''>('')
  const [indo, setIndo] = useState(false)
  const escolhido = est.data?.itens.find(i => i.id === item)
  const fichaEscolhida = useGet<Ficha>(escolhido?.tracking === 'serie' ? `/estoque/${escolhido.id}` : null)
  const nossas = (fichaEscolhida.data?.unidades || []).filter(u => !u.client_id && EM_CASA.includes(u.status))
  const cob = useGet<{ itens: Cobranca[]; total: number; sem_preco: number }>(`/estoque/cobrancas?client_id=${cid}`)
  const recarregar = () => { dele.reload(); est.reload(); cob.reload() }
  async function resolver(ch: Cobranca, acao: 'cobrada' | 'nao_cobrar' | 'preco') {
    let unit_price: number | undefined
    if (acao === 'preco') {
      const v = window.prompt(`Preço unitário de ${ch.name} (US$)`, ch.unit_price != null ? String(ch.unit_price) : '')
      if (v === null) return
      unit_price = Number(v.replace(',', '.'))
      if (!(unit_price >= 0)) { toast('Preço inválido.', 'warn'); return }
    }
    setIndo(true)
    try { await api.post(`/estoque/cobrancas/${ch.id}`, { acao, unit_price }); toast(acao === 'preco' ? 'Preço definido.' : acao === 'cobrada' ? 'Marcada como cobrada.' : 'Não será cobrada.', 'ok'); recarregar() }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setIndo(false) }
  }

  async function assinalar() {
    if (!escolhido) return
    const serie = escolhido.tracking === 'serie'
    const q = num(qtd)
    if (!serie && (!q || q <= 0)) { toast('Informe quantos são dele.', 'warn'); return }
    setIndo(true)
    try {
      await api.post('/estoque/assinalar', { item_id: escolhido.id, client_id: cid, qty: serie ? null : q, unit_id: serie ? unidade || null : null, local })
      toast(`Assinalado para ${nome}.`, 'ok'); setItem(''); setQtd(''); setUnidade(''); recarregar()
    } catch (e) { toast((e as ApiError).message, 'crit') } finally { setIndo(false) }
  }
  async function devolver(corpo: Record<string, unknown>) {
    setIndo(true)
    try { await api.post('/estoque/devolver', { client_id: cid, ...corpo }); toast('Voltou a ser da URACE.', 'ok'); recarregar() }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setIndo(false) }
  }

  if (dele.error) return <ErrorState error={dele.error} retry={dele.reload} />
  if (dele.loading && !dele.data) return <Loading rows={2} />
  const nada = !dele.data?.pecas.length && !dele.data?.unidades.length
  const disponiveis = (est.data?.itens || []).filter(i => i.tracking === 'serie' || i.nosso > 0)
  return <div>
    {!!cob.data?.itens.length && <div style={{ marginBottom: 16 }}>
      <h4 style={{ margin: '0 0 6px' }}>Peças do estoque usadas — a cobrar <span className="muted">· ${cob.data.total.toFixed(2)}{cob.data.sem_preco ? ` + ${cob.data.sem_preco} sem preço` : ''}</span></h4>
      <p className="small muted" style={{ marginTop: 0 }}>Entram na próxima invoice deste cliente pelo preço final do estoque. Quando a invoice chega do QuickBooks com a peça, sai daqui sozinha.</p>
      <div className="tbl">{cob.data.itens.map(ch => <div className="tr" key={ch.id}>
        <div className="grow"><b>{ch.qty}× {ch.name}</b>
          <div className="small muted">usada em {quando(ch.created_at)}{ch.por ? ` · ${ch.por}` : ''}{ch.notes ? ` · ${ch.notes}` : ''}</div></div>
        {ch.unit_price != null ? <Chip tone="accent">${(ch.total ?? 0).toFixed(2)}</Chip> : <Chip tone="warn">sem preço</Chip>}
        {can('MANAGER') && <>
          <button className="btn ghost sm" disabled={indo} onClick={() => resolver(ch, 'preco')}>preço</button>
          <button className="btn ghost sm" disabled={indo} onClick={() => resolver(ch, 'cobrada')} title="já foi cobrada por fora">cobrada</button>
          <button className="btn ghost sm" disabled={indo} onClick={() => resolver(ch, 'nao_cobrar')} title="garantia, cortesia">não cobrar</button>
        </>}
      </div>)}</div>
    </div>}
    {nada ? <Empty title="Nada guardado">Nenhuma peça deste cliente está com a gente.</Empty>
      : <div className="tbl">
        {dele.data!.pecas.map(p => <div className="tr" key={`l${p.id}`}>
          <div className="grow"><b>{p.name}</b><div className="small muted">{[p.subcategory, p.size].filter(Boolean).join(' · ')}{p.subcategory || p.size ? ' · ' : ''}{p.local}</div></div>
          <Chip tone="info">{p.qty} {p.unit}</Chip>
          {can('MANAGER') && <button className="btn ghost sm" disabled={indo} onClick={() => devolver({ item_id: p.item_id, qty: p.qty, local: p.local_code })}>devolver p/ URACE</button>}
        </div>)}
        {dele.data!.unidades.map(u => <div className="tr" key={`u${u.id}`}>
          <div className="grow"><b>{u.name}</b><div className="small muted">série {u.serial}{u.local ? ` · ${u.local}` : ''}</div></div>
          {can('MANAGER') && <button className="btn ghost sm" disabled={indo} onClick={() => devolver({ item_id: u.item_id, unit_id: u.id, local: u.local_code || 'sede' })}>devolver p/ URACE</button>}
        </div>)}
      </div>}
    {can('OPERATOR') && <>
      <h4 style={{ margin: '14px 0 6px' }}>Assinalar peça do estoque para {nome}</h4>
      <div className="row gap wrap">
        <label className="fld grow"><span>Peça</span>
          <select value={item} onChange={e => { setItem(e.target.value ? Number(e.target.value) : ''); setUnidade('') }}>
            <option value="">escolha…</option>
            {disponiveis.map(i => <option key={i.id} value={i.id}>{i.name}{i.size ? ` · ${i.size}` : ''}{i.tracking === 'quantidade' ? ` (${i.nosso} ${i.unit} da URACE)` : ''}</option>)}
          </select></label>
        {escolhido?.tracking === 'serie'
          ? <label className="fld grow"><span>Qual unidade</span>
            <select value={unidade} onChange={e => setUnidade(e.target.value ? Number(e.target.value) : '')}>
              <option value="">—</option>{nossas.map(u => <option key={u.id} value={u.id}>série {u.serial}</option>)}</select></label>
          : <label className="fld grow"><span>Quantos</span>
            <input type="number" inputMode="decimal" min={0} value={qtd} onChange={e => setQtd(e.target.value)} placeholder={escolhido?.unit || ''} /></label>}
        {(est.data?.locais.length || 0) > 1 && <label className="fld grow"><span>Onde</span>
          <select value={local} onChange={e => setLocal(e.target.value)}>{est.data!.locais.map(l => <option key={l.code} value={l.code}>{l.name}</option>)}</select></label>}
      </div>
      <button className="btn" disabled={indo || !escolhido} onClick={assinalar}>{indo ? 'Salvando…' : 'Assinalar'}</button>
    </>}
  </div>
}
