/* Balcão (#87): o leitor de QR e de código de barras.
 *
 * Dono, 05/10: o mecânico lê o QR do cliente e o código de barras da peça, e a peça já entra
 * na invoice de peças do dia daquele cliente, que nasce no QuickBooks na hora e NÃO é enviada
 * sozinha. Peça do cliente vai para o estoque dele (modo GUARDAR), e a diferença tem de ser
 * evidente: cada modo tem a sua cor, o aviso fica no topo e trocar pede um toque de propósito.
 *
 * O leitor (coletor Android) digita o código no campo e aperta Enter, como um teclado. A
 * câmera é a alternativa, em qualquer celular: o leitor nativo do Chrome ou, no iPhone, o ZXing. */
import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, ApiError, qs } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { irComPasse, pedirPasse, restaurarReferrer } from '../auth/passe'
import { Banner, Chip, Empty, PageHeader, Scrim, Section } from '../components/ui'
import { FotoPeca } from '../components/FotoPeca'
import { useToast } from '../components/Toast'
import { tr } from '../i18n'
import { CAMERA, novoDetector, temCamera, vibrar } from '../components/Leitor'
import { Picker } from '../components/Unir'
import type { Client } from '../api/types'

type Modo = 'cobrar' | 'guardar'
interface Cliente { id: number; nome: string; responsavel: string }
interface Item { id: number; name: string; price: number | null; unit: string; qbo_item_id: string | null; qbo_item_name: string | null
  codigos: string[]; nosso: number; do_cliente?: number }
interface Linha { id: number; qty: number; unit_price: number; name: string; total: number }
interface InvPecas { id: number; client_id: number; cliente: string | null; service_date: string; status: string; qbo_invoice_id: string | null
  doc_number: string | null; total: number; qbo_error: string | null; sent_to: string | null; linhas: Linha[]
  paga?: boolean; cartao?: boolean; paid_at?: string | null }
interface Leitura { id: number; name: string; mode: string; qty: number; at: string; undone_at: string | null; por: string | null; travada?: number }
interface Estado { cliente: Cliente; data: string; invoices: InvPecas[]; leituras: Leitura[]; gerente: boolean
  guardado: { item_id: number; name: string; qty: number; local: string }[] }
type Lido = { tipo: 'cliente'; cliente: Cliente } | { tipo: 'peca'; codigo: string; item: Item } | { tipo: 'desconhecido'; codigo: string }

const usd = (n: number) => n.toLocaleString('en-US', { style: 'currency', currency: 'USD' })
const LOCAIS: [string, string][] = [['sede', tr("Galpão")], ['trailer', tr("Trailer")], ['pista', tr("Pista")]]
const MODO_TXT: Record<string, string> = { cobrar: tr("cobrada"), guardar: tr("guardada para o cliente"), usar_do_cliente: tr("usada do estoque do cliente") }
const lerLocal = () => { try { return localStorage.getItem('balcao.local') || 'sede' } catch { return 'sede' } }

function Camera({ onLer, onFechar }: { onLer: (t: string) => void; onFechar: () => void }) {
  const video = useRef<HTMLVideoElement>(null)
  const [erro, setErro] = useState<string | null>(temCamera() ? null
    : 'Este navegador não abre a câmera aqui. Abra o painel pelo endereço https e permita a câmera.')
  const [pronto, setPronto] = useState(false)
  useEffect(() => {
    let parar = false, stream: MediaStream | null = null
    if (!temCamera()) return
    ;(async () => {
      try {
        const [det, s] = await Promise.all([novoDetector(),
          navigator.mediaDevices.getUserMedia(CAMERA)])
        stream = s
        if (parar || !video.current) { s.getTracks().forEach(t => t.stop()); return }
        video.current.srcObject = s; await video.current.play(); setPronto(true)
        while (!parar) {
          try { const r = await det.detect(video.current); if (r[0]?.rawValue) { vibrar(40); onLer(r[0].rawValue); return } } catch { /* quadro ruim */ }
          await new Promise(ok => setTimeout(ok, 180))
        }
      } catch (e) {
        if (!parar) setErro((e as Error)?.name === 'NotAllowedError'
          ? tr("A câmera foi negada. Libere a câmera para este site nas configurações do navegador e tente de novo.")
          : tr("Não deu para abrir a câmera."))
      }
    })()
    return () => { parar = true; stream?.getTracks().forEach(t => t.stop()) }
  }, [onLer])
  return <Scrim onMouseDown={onFechar}><div className="modal" style={{ maxWidth: 480 }} onMouseDown={e => e.stopPropagation()}>
    <h2 className="h3">{tr("Apontar para o código")}</h2>
    {erro ? <Banner tone="warn">{erro}</Banner> : <>
      <video ref={video} className="balcao-video" muted playsInline aria-label={tr("Imagem da câmera")} />
      <p className="small muted" style={{ margin: '8px 0 0' }}>{pronto ? tr("QR do cliente ou código de barras da peça: segure parado até vibrar.") : tr("Abrindo a câmera…")}</p>
    </>}
    <div className="row" style={{ justifyContent: 'flex-end', marginTop: 12 }}><button className="btn" onClick={onFechar}>{tr("Fechar")}</button></div>
  </div></Scrim>
}

/** Código que o sistema ainda não conhece: diz que peça é. O gerente já cria o item no QuickBooks. */
function CodigoNovo({ codigo, gerente, onFeito, onFechar }: { codigo: string; gerente: boolean; onFeito: (i: Item) => void; onFechar: () => void }) {
  const toast = useToast()
  const [itens, setItens] = useState<{ id: number; name: string }[]>([])
  const [prat, setPrat] = useState<{ code: string; nome: string }[]>([])
  const [cats, setCats] = useState<{ id: string; nome: string }[]>([])
  const [f, setF] = useState({ item_id: '', nome: '', category: '', price: '', qbo_categoria_id: '' })
  const [indo, setIndo] = useState(false)
  const [qboFora, setQboFora] = useState(false)
  const [foto, setFoto] = useState<File | null>(null)
  const [previa, setPrevia] = useState<string | null>(null)
  function escolher(arq: File | null) {
    setFoto(arq)
    setPrevia(old => { if (old) URL.revokeObjectURL(old); return arq ? URL.createObjectURL(arq) : null })
  }
  useEffect(() => {
    api.get<{ itens: { id: number; name: string }[]; prateleiras: { code: string; nome: string }[] }>('/estoque')
      .then(r => { setItens(r.itens); setPrat(r.prateleiras) }).catch(() => undefined)
    if (gerente) api.get<{ categorias: { id: string; nome: string }[]; conectado: boolean }>('/balcao/categorias')
      .then(r => { setCats(r.categorias); setQboFora(!r.conectado) }).catch(() => setQboFora(true))
  }, [gerente])
  async function salvar(e: FormEvent) {
    e.preventDefault(); setIndo(true)
    try {
      const r = await api.post<{ item: Item; aviso: string | null }>('/balcao/codigos', {
        codigo, item_id: f.item_id ? Number(f.item_id) : null, nome: f.nome || null, category: f.category || null,
        price: gerente && f.price ? Number(f.price) : null, qbo_categoria_id: gerente && f.qbo_categoria_id ? f.qbo_categoria_id : null })
      // a foto vai depois do código: se ela falhar, o código continua cadastrado
      let semFoto = false
      if (foto) {
        const fd = new FormData(); fd.append('foto', foto)
        try { await api.postForm(`/estoque/item/${r.item.id}/foto`, fd) } catch (er) { semFoto = true; toast(tr("Código cadastrado, mas a foto não: {0}", (er as ApiError).message), 'warn') }
      }
      if (r.aviso) toast(r.aviso, 'crit'); else if (!semFoto) toast(foto ? tr("Código e foto cadastrados.") : tr("Código cadastrado."), 'ok')
      onFeito(r.item)
    } catch (er) { toast((er as ApiError).message, 'crit') } finally { setIndo(false) }
  }
  return <Scrim onMouseDown={onFechar}><form className="modal stack" style={{ maxWidth: 520, gap: 12 }} onMouseDown={e => e.stopPropagation()} onSubmit={salvar}>
    <h2 className="h3">{tr("Código novo")}</h2>
    <p className="small muted" style={{ margin: 0 }}>{tr("O sistema ainda não conhece")} <span className="mono">{codigo}</span>{tr(". Diga que peça é: daqui em diante, ler este código já identifica a peça.")}</p>
    <label className="fld"><span>{tr("Peça que já está no estoque")}</span>
      <select value={f.item_id} onChange={e => setF({ ...f, item_id: e.target.value })}>
        <option value="">{tr("— é uma peça nova —")}</option>{itens.map(i => <option key={i.id} value={i.id}>{i.name}</option>)}</select></label>
    {!f.item_id && <>
      <label className="fld"><span>{tr("Nome da peça nova")}</span><input value={f.nome} onChange={e => setF({ ...f, nome: e.target.value })} placeholder={tr("Front bumper Tony Kart")} /></label>
      <label className="fld"><span>{tr("Prateleira")}</span><select value={f.category} onChange={e => setF({ ...f, category: e.target.value })}>
        <option value="">—</option>{prat.map(p => <option key={p.code} value={p.code}>{p.nome}</option>)}</select></label>
    </>}
    <FotoPeca previa={previa} onFile={escolher} rotulo={f.item_id ? tr("Foto da peça (troca a atual)") : tr("Foto da peça")} />
    {gerente ? <>
      <label className="fld"><span>{tr("Preço final (US$)")}</span><input inputMode="decimal" value={f.price} onChange={e => setF({ ...f, price: e.target.value })} /></label>
      <label className="fld"><span>{tr("Categoria no QuickBooks")} <i>{tr("cria o item lá agora")}</i></span><select value={f.qbo_categoria_id} onChange={e => setF({ ...f, qbo_categoria_id: e.target.value })}>
        <option value="">{tr("— depois —")}</option>{cats.map(c => <option key={c.id} value={c.id}>{c.nome}</option>)}</select></label>
      {qboFora && <p className="small muted" style={{ margin: 0 }}>{tr("QuickBooks não conectado: salve o código agora e crie o item lá depois.")}</p>}
    </> : <p className="small muted" style={{ margin: 0 }}>{tr("Preço e item do QuickBooks: o gerente completa antes de cobrar.")}</p>}
    <div className="row" style={{ justifyContent: 'flex-end' }}>
      <button type="button" className="btn" onClick={onFechar}>{tr("Cancelar")}</button>
      <button className="btn primary" disabled={indo || (!f.item_id && !f.nome.trim())}>{indo ? <span className="spin" /> : tr("Salvar código")}</button></div>
  </form></Scrim>
}

/** Peça sem item no QuickBooks ou sem preço: o gerente liga a um item que já existe lá, ou cria
 *  dentro da categoria (#206: antes, só criar; e só no balcão com cliente aberto). */
type ItemMin = Pick<Item, 'id' | 'name' | 'price'> & { qbo_item_id?: string | null }
function ItemQbo({ item, onFeito, onFechar }: { item: ItemMin; onFeito: () => void; onFechar: () => void }) {
  const toast = useToast()
  const [cats, setCats] = useState<{ id: string; nome: string }[]>([])
  const [existentes, setExistentes] = useState<{ id: string; name: string; full_name: string | null; price: number | null }[]>([])
  const [como, setComo] = useState<'ligar' | 'criar'>('ligar')
  const [cat, setCat] = useState('')
  const [qid, setQid] = useState(item.qbo_item_id || '')
  const [busca, setBusca] = useState('')
  const [preco, setPreco] = useState(item.price != null ? String(item.price) : '')
  const [indo, setIndo] = useState(false)
  useEffect(() => {
    api.get<{ categorias: { id: string; nome: string }[]; itens: { id: string; name: string; full_name: string | null; price: number | null }[]; conectado: boolean }>('/balcao/categorias')
      .then(r => { setCats(r.categorias); setExistentes(r.itens); if (!r.conectado) toast(tr("QuickBooks não está conectado: não dá para criar o item agora."), 'crit') })
      .catch(e => toast((e as ApiError).message, 'crit'))
  }, [toast])
  const termo = busca.trim().toLowerCase()
  const lista = (termo ? existentes.filter(x => (x.full_name || x.name).toLowerCase().includes(termo)) : existentes).slice(0, 80)
  async function salvar() {
    setIndo(true)
    try {
      await api.post(`/balcao/itens/${item.id}/quickbooks`, como === 'ligar'
        ? { qbo_item_id: qid, price: preco ? Number(preco) : null }
        : { categoria_id: cat, price: preco ? Number(preco) : null })
      toast(como === 'ligar' ? tr("Peça ligada ao item do QuickBooks.") : tr("Item criado no QuickBooks."), 'ok'); onFeito()
    } catch (e) { toast((e as ApiError).message, 'crit') } finally { setIndo(false) }
  }
  const pronto = !!preco && (como === 'ligar' ? !!qid : !!cat)
  return <Scrim onMouseDown={onFechar}><div className="modal stack" style={{ maxWidth: 520, gap: 12 }} onMouseDown={e => e.stopPropagation()}>
    <h2 className="h3">{item.name} {tr("no QuickBooks")}</h2>
    <div className="row wrap" role="radiogroup" aria-label={tr("Como ligar")} style={{ gap: 8 }}>
      <button type="button" role="radio" aria-checked={como === 'ligar'} className={`btn sm${como === 'ligar' ? ' primary' : ''}`} onClick={() => setComo('ligar')}>{tr("Item que já existe")}</button>
      <button type="button" role="radio" aria-checked={como === 'criar'} className={`btn sm${como === 'criar' ? ' primary' : ''}`} onClick={() => setComo('criar')}>{tr("Criar item novo")}</button>
    </div>
    {como === 'ligar' ? <>
      <label className="fld"><span>{tr("Buscar no catálogo")}</span><input value={busca} onChange={e => setBusca(e.target.value)} placeholder={tr("bumper, chain, MG…")} /></label>
      <label className="fld"><span>{tr("Item do QuickBooks")}</span><select value={qid} onChange={e => { setQid(e.target.value); const x = existentes.find(i => i.id === e.target.value); if (x?.price != null && !preco) setPreco(String(x.price)) }}>
        <option value="">—</option>{lista.map(x => <option key={x.id} value={x.id}>{x.full_name || x.name}{x.price != null ? ` · US$ ${x.price.toFixed(2)}` : ''}</option>)}</select></label>
    </> : <label className="fld"><span>{tr("Categoria")}</span><select value={cat} onChange={e => setCat(e.target.value)}><option value="">—</option>{cats.map(c => <option key={c.id} value={c.id}>{c.nome}</option>)}</select></label>}
    <label className="fld"><span>{tr("Preço final (US$)")}</span><input inputMode="decimal" value={preco} onChange={e => setPreco(e.target.value)} /></label>
    <div className="row" style={{ justifyContent: 'flex-end' }}><button className="btn" onClick={onFechar}>{tr("Cancelar")}</button>
      <button className="btn primary" disabled={indo || !pronto} onClick={salvar}>{indo ? <span className="spin" /> : como === 'ligar' ? tr("Ligar") : tr("Criar item")}</button></div>
  </div></Scrim>
}

/* Cartão no balcão (06/10; aparece por padrão, CC_BALCAO_CARTAO=0 esconde): o cartão passa no QuickBooks
 * GoPayment, no leitor Bluetooth, em "Invoice payment" → cliente → esta invoice → Charge. O
 * GoPayment paga a PRÓPRIA invoice no QuickBooks (nada em dobro) e o número do cartão nunca
 * passa pelo Command Center. Aqui: o que procurar no app, o botão que abre o app e a conferência. */
const GOPAYMENT = 'intent://#Intent;package=com.intuit.intuitgopayment;S.browser_fallback_url='
  + encodeURIComponent('https://play.google.com/store/apps/details?id=com.intuit.intuitgopayment') + ';end'
// #206: o link "intent://" só o Android entende; no iPhone o app abre pela tela de início
const ANDROID = typeof navigator !== 'undefined' && /Android/i.test(navigator.userAgent)

function CobrarNoCartao({ p, onFechar, onPago }: { p: InvPecas; onFechar: () => void; onPago: () => void }) {
  const toast = useToast()
  const [indo, setIndo] = useState(false)
  const [saldo, setSaldo] = useState<number | null>(null)
  async function conferir() {
    setIndo(true)
    try {
      const r = await api.post<{ paga: boolean; saldo: number }>(`/balcao/invoices/${p.id}/conferir-pagamento`)
      if (r.paga) { toast(tr("Pago no cartão: o QuickBooks já marcou a invoice."), 'ok'); onPago(); onFechar() }
      else setSaldo(r.saldo)
    } catch (e) { toast((e as ApiError).message, 'crit') } finally { setIndo(false) }
  }
  return <Scrim onMouseDown={onFechar}><div className="modal stack" style={{ maxWidth: 440, gap: 12 }} onMouseDown={e => e.stopPropagation()}>
    <h3 style={{ margin: 0 }}>{tr("Cobrar no cartão")}</h3>
    <div className="card card-b" style={{ textAlign: 'center' }}>
      <div className="small muted">{p.cliente || tr("Cliente")}{p.doc_number ? tr(" · invoice {0}", p.doc_number) : ''}</div>
      <div style={{ fontSize: 34, fontWeight: 700 }} className="mono">{usd(p.total)}</div>
    </div>
    <ol className="small" style={{ margin: 0, paddingLeft: 20, lineHeight: 1.6 }}>
      <li>{ANDROID ? tr("Abra o QuickBooks GoPayment (botão abaixo).") : tr("Abra o app QuickBooks GoPayment no aparelho.")}</li>
      <li>{tr("Toque em")} <b>+</b> {tr("e escolha")} <b>{tr("Invoice payment")}</b>.</li>
      <li>{tr("Procure")} <b>{p.cliente || tr("o cliente")}</b> {tr("e escolha a invoice")} <b>{p.doc_number || tr("de peças de hoje")}</b> {tr("de")} <b>{usd(p.total)}</b>.</li>
      <li>{tr("Toque em")} <b>{tr("Charge")}</b> {tr("e passe o cartão no leitor (chip ou aproximação).")}</li>
      <li>{tr("Volte aqui e toque em")} <b>{tr("Já passei o cartão")}</b>.</li>
    </ol>
    {saldo !== null && <Banner tone="warn">{tr("O QuickBooks ainda mostra saldo de")} {usd(saldo)} {tr("nesta invoice. Confira no GoPayment se a cobrança foi aprovada e tente de novo.")}</Banner>}
    <div className="row wrap" style={{ gap: 8, justifyContent: 'flex-end' }}>
      <button className="btn" onClick={onFechar}>{tr("Fechar")}</button>
      {ANDROID && <a className="btn" href={GOPAYMENT}>{tr("Abrir o GoPayment")}</a>}
      <button className="btn primary" disabled={indo} onClick={conferir}>{indo ? <span className="spin" /> : tr("Já passei o cartão")}</button>
    </div>
  </div></Scrim>
}

function CartaoInvoice({ p, gerente, onMudou }: { p: InvPecas; gerente: boolean; onMudou: () => void }) {
  const toast = useToast()
  const [indo, setIndo] = useState(false)
  const [cartao, setCartao] = useState(false)
  async function acao(qual: 'sincronizar' | 'enviar') {
    setIndo(true)
    try { await api.post(`/balcao/invoices/${p.id}/${qual}`); toast(qual === 'enviar' ? tr("Invoice enviada pelo QuickBooks.") : tr("Atualizada no QuickBooks."), 'ok'); onMudou() }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setIndo(false) }
  }
  return <div className="card card-b stack" style={{ gap: 8 }}>
    <div className="row wrap" style={{ gap: 8 }}>
      <b className="grow">{tr("Peças de")} {p.service_date.slice(5, 7)}/{p.service_date.slice(8, 10)}{p.cliente ? ` · ${p.cliente}` : ''}</b>
      {p.status === 'enviada' ? <Chip tone="ok">{tr("enviada")}{p.sent_to ? tr(" para {0}", p.sent_to) : ''}</Chip> : p.status === 'anulada' ? <Chip tone="neutral">{tr("anulada")}</Chip>
        : <Chip tone="warn">{tr("aberta · não enviada")}</Chip>}
      {p.paga && <Chip tone="ok">{tr("paga")}</Chip>}
      {p.doc_number && <span className="mono small">{p.doc_number}</span>}
    </div>
    {p.qbo_error && <Banner tone="crit">{tr("QuickBooks:")} {p.qbo_error}</Banner>}
    {p.linhas.length > 0 && <div className="tbl">{p.linhas.map(l => <div className="tr" key={l.id}><span className="grow">{l.name}</span>
      <span className="small muted">{l.qty} {tr("×")} {usd(l.unit_price)}</span><b className="mono">{usd(l.total)}</b></div>)}</div>}
    <div className="row wrap" style={{ gap: 8 }}><b className="grow">{tr("Total")} {usd(p.total)}</b>
      {p.status === 'aberta' && p.qbo_error && <button className="btn sm" disabled={indo} onClick={() => acao('sincronizar')}>{tr("Tentar de novo")}</button>}
    </div>
    {/* Dono, 06/10: as duas vias — montar a invoice e enviar, ou cobrar no leitor de cartão */}
    {!p.paga && p.status !== 'anulada' && p.total > 0 && p.qbo_invoice_id && !p.qbo_error && <div className="stack" style={{ gap: 6 }}>
      <span className="small muted">{tr("Como o cliente paga?")}</span>
      <div className="row wrap" style={{ gap: 8 }}>
        {p.status === 'aberta' && (gerente
          ? <button className="btn sm" disabled={indo} onClick={() => acao('enviar')}>{tr("Enviar invoice por e-mail")}</button>
          : <span className="small muted">{tr("Enviar invoice: o gerente envia no fim do dia.")}</span>)}
        {p.status === 'enviada' && <span className="small muted">{tr("Invoice enviada: o cliente paga pelo link do e-mail.")}</span>}
        {p.cartao && <button className="btn sm primary" onClick={() => setCartao(true)}>{tr("Cobrar no cartão")}</button>}
      </div>
    </div>}
    {cartao && <CobrarNoCartao p={p} onFechar={() => setCartao(false)} onPago={onMudou} />}
  </div>
}

function AEnviar() {
  const { can } = useAuth()
  const [d, setD] = useState<{ itens: InvPecas[]; total: number } | null>(null)
  const [limite, setLimite] = useState(50)
  const carregar = useCallback(() => { api.get<{ itens: InvPecas[]; total: number }>(`/balcao/invoices${qs({ limit: limite })}`).then(setD).catch(() => setD({ itens: [], total: 0 })) }, [limite])
  useEffect(() => { carregar() }, [carregar])
  return <Section title={tr("Invoices de peças para enviar")} count={d?.total}>
    {!d ? <span className="spin" /> : !d.itens.length ? <Empty title={tr("Nada para enviar")}>{tr("As invoices de peças abertas aparecem aqui até alguém enviar.")}</Empty>
      : <div className="stack" style={{ gap: 10 }}>{d.itens.map(p => <CartaoInvoice key={p.id} p={p} gerente={can('MANAGER')} onMudou={carregar} />)}
        {d.total > d.itens.length && <button className="btn ghost" onClick={() => setLimite(l => Math.min(200, l + 50))}>{tr("Carregar mais")}</button>}</div>}
  </Section>
}

/* #180 → #206: a leitura do celular com cliente vai direto para a OS (dono, 13/10: "Não tem essa de ter
 * que confirmar depois"). Aqui ficam só as que não puderam ir, com o motivo: o gerente resolve e
 * confirma — aí entra no estoque e na invoice de peças do dia da leitura — ou descarta. */
interface Pend { id: number; code: string; peca: string | null; pilot_name: string | null; client_id: number | null
  service_date: string; at: string; por: string | null; motivo?: string | null
  item?: { id: number; name: string; price: number | null; qbo_item_id: string | null; do_cliente: number; nosso?: number } }

function ItemRevisao({ p, onMudou }: { p: Pend; onMudou: (r: { itens: Pend[]; total: number } | null) => void }) {
  const toast = useToast()
  const [cliente, setCliente] = useState<Client | null>(null)
  const [item, setItem] = useState<Item | null>(null)
  const [novo, setNovo] = useState(false)
  const [doCliente, setDoCliente] = useState<string | null>(null)
  const [indo, setIndo] = useState(false)
  const [local, setLocal] = useState(lerLocal)          // #206: de onde a peça saiu (antes, sempre o galpão)
  const [qbo, setQbo] = useState<ItemMin | null>(null)  // #206: sem item no QuickBooks ou sem preço, resolve aqui
  const [depois, setDepois] = useState<{ modo: string; confirmado: boolean } | null>(null)
  const temItem = !!(p.item || item)
  const temCliente = !!(p.client_id || cliente)
  const it: ItemMin | null = item ? { id: item.id, name: item.name, price: item.price, qbo_item_id: item.qbo_item_id } : p.item ? p.item : null
  async function confirmar(modo: string, confirmado = false) {
    setIndo(true)
    try {
      const r = await api.post<{ itens: Pend[]; total: number }>(`/balcao/revisao/${p.id}/confirmar`,
        { modo, client_id: cliente?.id ?? null, item_id: item?.id ?? null, confirmado, local })
      toast(tr("Peça confirmada: {0}.", MODO_TXT[modo]), 'ok'); onMudou(r)
    } catch (e) {
      const er = e as ApiError
      if (er.motivo === 'tem_do_cliente') setDoCliente(er.message)
      else if (it && (er.motivo === 'precisa_item_qbo' || /preço final/.test(er.message))) { setDepois({ modo, confirmado }); setQbo(it) }
      else toast(er.message, 'crit')
    } finally { setIndo(false) }
  }
  async function descartar() {
    setIndo(true)
    try { onMudou(await api.post<{ itens: Pend[]; total: number }>(`/balcao/revisao/${p.id}/descartar`, {})); toast(tr("Descartada."), 'ok') }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setIndo(false) }
  }
  const nome = item?.name || p.item?.name
  return <div className="card card-b stack" style={{ gap: 8 }}>
    <div className="row wrap" style={{ gap: 8 }}>
      <div className="grow"><b>{nome || tr("Código novo")}</b> <span className="mono small muted">{p.code}</span>
        <div className="small muted">{p.pilot_name || tr("sem piloto")} · {p.service_date} · {tr("lida por {0}", p.por || '—')}
          {p.item?.price != null ? ` · ${usd(p.item.price)}` : ''}</div></div>
      {!temItem && <Chip tone="warn">{tr("código novo")}</Chip>}
      {!temCliente && <Chip tone="warn">{tr("sem cliente")}</Chip>}
      {p.item && !p.item.qbo_item_id && <Chip tone="warn">{tr("sem item no QuickBooks")}</Chip>}
      {p.item && p.item.price == null && <Chip tone="warn">{tr("sem preço")}</Chip>}
      {p.item && (p.item.nosso ?? 1) <= 0 && <Chip tone="warn">{tr("sem saldo na prateleira")}</Chip>}
    </div>
    {p.motivo && <p className="small" style={{ margin: 0 }}><b>{tr("Por que não foi direto para a OS:")}</b> {p.motivo}</p>}
    {p.item && (p.item.nosso ?? 1) <= 0 && <p className="small muted" style={{ margin: 0 }}>{tr("A URACE não tem esta peça contada no estoque: para cobrar, conte a prateleira antes (Contar o estoque, nesta tela).")}</p>}
    {!p.client_id && <Picker label={tr("Cliente desta peça")} value={cliente} onPick={setCliente} />}
    {!temItem && <button className="btn sm" onClick={() => setNovo(true)}>{tr("Dizer que peça é")}</button>}
    {it && (!it.qbo_item_id || it.price == null) && <button className="btn sm" onClick={() => setQbo(it)}>{tr("Ligar ao QuickBooks e definir o preço")}</button>}
    {doCliente && <Banner tone="warn">{doCliente}</Banner>}
    <label className="fld" style={{ maxWidth: 220 }}><span>{tr("A peça saiu de")}</span>
      <select value={local} onChange={e => setLocal(e.target.value)}>{LOCAIS.map(([k, r]) => <option key={k} value={k}>{r}</option>)}</select></label>
    <div className="row wrap" style={{ gap: 8 }}>
      <button className="btn sm primary" disabled={indo || !temItem || !temCliente} onClick={() => confirmar('cobrar', !!doCliente)}>{doCliente ? tr("Cobrar mesmo assim") : tr("Cobrar")}</button>
      <button className="btn sm balcao-btn-guardar" disabled={indo || !temItem || !temCliente} onClick={() => confirmar('guardar')}>{tr("Guardar para o cliente")}</button>
      {(doCliente || (p.item?.do_cliente ?? 0) > 0) && <button className="btn sm" disabled={indo} onClick={() => confirmar('usar_do_cliente')}>{tr("Usar a do cliente")}</button>}
      <button className="btn sm ghost" disabled={indo} onClick={descartar}>{tr("Descartar")}</button>
    </div>
    {novo && <CodigoNovo codigo={p.code} gerente onFechar={() => setNovo(false)} onFeito={i => { setNovo(false); setItem(i) }} />}
    {qbo && <ItemQbo item={qbo} onFechar={() => { setQbo(null); setDepois(null) }}
      onFeito={() => { setQbo(null); const d = depois; setDepois(null); if (d) confirmar(d.modo, d.confirmado); else onMudou(null) }} />}
  </div>
}

function Revisao() {
  const [d, setD] = useState<{ itens: Pend[]; total: number } | null>(null)
  const [limite, setLimite] = useState(50)
  const carregar = useCallback(() => { api.get<{ itens: Pend[]; total: number }>(`/balcao/revisao${qs({ limit: limite })}`).then(setD).catch(() => setD({ itens: [], total: 0 })) }, [limite])
  useEffect(() => { carregar() }, [carregar])
  return <Section title={tr("Revisão: lidas no celular")} count={d?.total}>
    {!d ? <span className="spin" /> : !d.itens.length ? <Empty title={tr("Nada para revisar")}>{tr("A leitura do celular vai direto para a OS do cliente. Aqui aparece só a que precisa de você (código novo, sem cliente, sem preço, sem saldo).")}</Empty>
      : <div className="stack" style={{ gap: 10 }}>{d.itens.map(p => <ItemRevisao key={p.id} p={p} onMudou={r => r ? setD(r) : carregar()} />)}
        {d.total > d.itens.length && <button className="btn ghost" onClick={() => setLimite(l => Math.min(200, l + 50))}>{tr("Carregar mais")}</button>}</div>}
  </Section>
}

/* #206: o estoque de produção estava todo em zero, nunca contado — e sem saldo o balcão não cobra
 * (D-2026-10-05: "primeiro conte ou dê entrada"). Contar a prateleira: ler a peça (ou a etiqueta),
 * digitar quanto tem, gravar; o próximo item já aparece. E a peça sem código ganha a etiqueta URACE. */
interface Contado { id: number; nome: string; qty: number; antes: number }
function ContarEstoque() {
  const toast = useToast()
  const [aberto, setAberto] = useState(false)
  const [local, setLocal] = useState(lerLocal)
  const [texto, setTexto] = useState('')
  const [camera, setCamera] = useState(false)
  const [atual, setAtual] = useState<Item | null>(null)
  const [qtd, setQtd] = useState('')
  const [novo, setNovo] = useState<string | null>(null)
  const [feitos, setFeitos] = useState<Contado[]>([])
  const [indo, setIndo] = useState(false)
  const [semCodigo, setSemCodigo] = useState(false)
  const campo = useRef<HTMLInputElement>(null)
  const qtdRef = useRef<HTMLInputElement>(null)
  const ler = useCallback(async (bruto: string) => {
    const t = bruto.trim(); setTexto(''); setCamera(false)
    if (!t) return
    try {
      const r = await api.get<Lido>(`/balcao/ler${qs({ codigo: t })}`)
      if (r.tipo === 'cliente') { vibrar(250); toast(tr("Este é o QR de um cliente. Para contar, leia a peça."), 'warn'); return }
      if (r.tipo === 'desconhecido') { setNovo(r.codigo); return }
      vibrar(40); setAtual(r.item); setQtd(''); setTimeout(() => qtdRef.current?.focus(), 30)
    } catch (e) { vibrar(250); toast((e as ApiError).message, 'crit') }
  }, [toast])
  async function gravar(e: FormEvent) {
    e.preventDefault()
    if (!atual || qtd.trim() === '') return
    setIndo(true)
    try {
      const r = await api.post<{ antes: number; depois: number }>('/estoque/contar', { item_id: atual.id, qty: Number(qtd), local })
      setFeitos(f => [{ id: atual.id, nome: atual.name, qty: r.depois, antes: r.antes }, ...f.filter(x => x.id !== atual.id)])
      toast(tr("{0}: {1} contado(s).", atual.name, r.depois), 'ok'); setAtual(null); setQtd('')
      setTimeout(() => campo.current?.focus(), 30)
    } catch (er) { toast((er as ApiError).message, 'crit') } finally { setIndo(false) }
  }
  return <Section title={tr("Contar o estoque")} count={feitos.length || undefined}>
    <p className="small muted" style={{ marginTop: 0 }}>{tr("Sem saldo contado, o balcão não cobra a peça. Leia a peça ou a etiqueta da prateleira, digite quanto tem e grave: o próximo item já aparece.")}</p>
    {!aberto ? <div className="row wrap" style={{ gap: 8 }}>
      <button className="btn primary" onClick={() => { setAberto(true); setTimeout(() => campo.current?.focus(), 30) }}>{tr("Começar a contar")}</button>
      <button className="btn" onClick={() => setSemCodigo(true)}>{tr("Peça sem código: etiqueta URACE")}</button>
    </div> : <div className="stack" style={{ gap: 10 }}>
      <label className="fld" style={{ maxWidth: 220 }}><span>{tr("Contando em")}</span>
        <select value={local} onChange={e => setLocal(e.target.value)}>{LOCAIS.map(([k, r]) => <option key={k} value={k}>{r}</option>)}</select></label>
      {!atual ? <form className="row wrap" style={{ gap: 8, alignItems: 'flex-end' }} onSubmit={e => { e.preventDefault(); ler(texto) }}>
        <label className="fld grow"><span>{tr("Leia a peça")}</span>
          <input ref={campo} value={texto} onChange={e => setTexto(e.target.value)} autoComplete="off" autoCapitalize="off" spellCheck={false} enterKeyHint="go" /></label>
        <button type="button" className="btn primary" onClick={() => setCamera(true)}>{tr("Ler com a câmera")}</button>
      </form> : <form className="card card-b stack" style={{ gap: 8 }} onSubmit={gravar}>
        <b>{atual.name}</b>
        <span className="small muted">{tr("O sistema diz que a URACE tem {0} (todos os locais).", atual.nosso)}</span>
        <label className="fld" style={{ maxWidth: 200 }}><span>{tr("Quanto tem aqui agora")}</span>
          <input ref={qtdRef} inputMode="decimal" value={qtd} onChange={e => setQtd(e.target.value)} /></label>
        <div className="row wrap" style={{ gap: 8 }}>
          <button className="btn primary" disabled={indo || qtd.trim() === ''}>{indo ? <span className="spin" /> : tr("Gravar contagem")}</button>
          <button type="button" className="btn ghost" onClick={() => { setAtual(null); setTimeout(() => campo.current?.focus(), 30) }}>{tr("Ler outra")}</button>
        </div>
      </form>}
      {feitos.length > 0 && <div className="card"><div className="tbl">{feitos.map(f => <div className="tr" key={f.id}>
        <span className="grow">{f.nome}</span><span className="small muted">{tr("era {0}", f.antes)}</span><b className="mono">{f.qty}</b></div>)}</div></div>}
      <div className="row wrap" style={{ gap: 8 }}>
        <button className="btn" onClick={() => setSemCodigo(true)}>{tr("Peça sem código: etiqueta URACE")}</button>
        <button className="btn ghost" onClick={() => { setAberto(false); setAtual(null) }}>{tr("Terminar")}</button>
      </div>
    </div>}
    {camera && <Camera onLer={ler} onFechar={() => setCamera(false)} />}
    {novo && <CodigoNovo codigo={novo} gerente={false} onFechar={() => setNovo(null)} onFeito={i => { setNovo(null); setAtual(i); setQtd(''); setTimeout(() => qtdRef.current?.focus(), 30) }} />}
    {semCodigo && <EtiquetaUrace onFechar={() => setSemCodigo(false)} />}
  </Section>
}

/** Peça sem código de fábrica: o sistema dá um código URACE (Code 128) e imprime a etiqueta. */
function EtiquetaUrace({ onFechar }: { onFechar: () => void }) {
  const toast = useToast()
  const [itens, setItens] = useState<{ id: number; name: string }[]>([])
  const [id, setId] = useState('')
  const [busca, setBusca] = useState('')
  const [indo, setIndo] = useState(false)
  const [pronto, setPronto] = useState<string | null>(null)
  useEffect(() => { api.get<{ itens: { id: number; name: string }[] }>('/estoque').then(r => setItens(r.itens)).catch(() => undefined) }, [])
  const termo = busca.trim().toLowerCase()
  const lista = (termo ? itens.filter(i => i.name.toLowerCase().includes(termo)) : itens).slice(0, 100)
  async function gerar() {
    setIndo(true)
    try {
      const r = await api.post<{ codigo: string }>(`/balcao/itens/${id}/codigo-urace`)
      setPronto(r.codigo)          // o PDF abre num toque (o iPhone bloqueia janela aberta depois da espera)
    } catch (e) { toast((e as ApiError).message, 'crit') } finally { setIndo(false) }
  }
  return <Scrim onMouseDown={onFechar}><div className="modal stack" style={{ maxWidth: 480, gap: 12 }} onMouseDown={e => e.stopPropagation()}>
    <h2 className="h3">{tr("Etiqueta URACE para peça sem código")}</h2>
    <p className="small muted" style={{ margin: 0 }}>{tr("A peça ganha um código de barras da URACE (62 × 29 mm). Daí em diante, ler a etiqueta já identifica a peça.")}</p>
    <label className="fld"><span>{tr("Buscar peça")}</span><input value={busca} onChange={e => setBusca(e.target.value)} /></label>
    <label className="fld"><span>{tr("Peça")}</span><select value={id} onChange={e => { setId(e.target.value); setPronto(null) }}>
      <option value="">—</option>{lista.map(i => <option key={i.id} value={i.id}>{i.name}</option>)}</select></label>
    {pronto && <Banner tone="ok">{tr("Código {0} pronto. Imprima e cole na peça ou na prateleira.", pronto)}</Banner>}
    <div className="row wrap" style={{ justifyContent: 'flex-end', gap: 8 }}><button className="btn" onClick={onFechar}>{pronto ? tr("Fechar") : tr("Cancelar")}</button>
      {pronto ? <a className="btn primary" href={`/ops/api/balcao/itens/${id}/etiqueta.pdf`} target="_blank" rel="noopener noreferrer">{tr("Abrir a etiqueta (PDF)")}</a>
        : <button className="btn primary" disabled={indo || !id} onClick={gerar}>{indo ? <span className="spin" /> : tr("Gerar código")}</button>}</div>
  </div></Scrim>
}

interface Produto { id: string; name: string; full_name: string | null; price: number | null; categoria: string; codigo: string }
interface Etiquetas { categorias: { nome: string; itens: number }[]; total: number; duplicatas: { motivo: string; itens: Produto[] }[]; atualizado: string | null }

/** Etiqueta QR de prateleira para cada produto do QuickBooks (#187): o mecânico aponta a câmera
 *  para a prateleira e a peça já entra; e as duplicatas do catálogo, só para conferir. */
function EtiquetasPrateleira() {
  const [d, setD] = useState<Etiquetas | null>(null)
  const [erro, setErro] = useState<string | null>(null)
  const [sel, setSel] = useState<string[]>([])
  const [verDup, setVerDup] = useState(false)
  useEffect(() => { api.get<Etiquetas>('/balcao/etiquetas').then(setD).catch(e => setErro((e as ApiError).message)) }, [])
  const total = d ? (sel.length ? d.categorias.filter(c => sel.includes(c.nome)).reduce((n, c) => n + c.itens, 0) : d.total) : 0
  const link = (formato: string) => `/ops/api/balcao/etiquetas.pdf${qs({ formato, categorias: sel.length ? sel.join('|') : undefined })}`
  const nomeCat = (c: string) => c || tr("Sem categoria")
  return <Section title={tr("Etiquetas QR das prateleiras")} count={d?.total}>
    {erro ? <Banner tone="crit">{erro}</Banner> : !d ? <span className="spin" /> : <div className="stack" style={{ gap: 12 }}>
      <p className="small muted" style={{ margin: 0 }}>{tr("Uma etiqueta por produto do QuickBooks, com o QR e o nome em inglês. Na primeira leitura, o balcão liga a peça ao item do QuickBooks.")}</p>
      <div className="et-cats" role="group" aria-label={tr("Categorias")}>
        {d.categorias.map(c => <button key={c.nome} className={`btn sm${sel.includes(c.nome) ? ' on' : ''}`} aria-pressed={sel.includes(c.nome)}
          onClick={() => setSel(v => v.includes(c.nome) ? v.filter(x => x !== c.nome) : [...v, c.nome])}>{nomeCat(c.nome)} <span className="muted">{c.itens}</span></button>)}
      </div>
      <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
        <a className="btn primary" href={link('folha')}>{tr("Baixar folha (8 por página) · {0}", total)}</a>
        <a className="btn" href={link('uma')}>{tr("Uma por página")}</a>
      </div>
      {d.duplicatas.length > 0 && <div>
        <button className="btn sm ghost" aria-expanded={verDup} onClick={() => setVerDup(v => !v)}>{tr("{0} possível(is) duplicata(s) no catálogo", d.duplicatas.length)}</button>
        {verDup && <><p className="small muted">{tr("Nomes que parecem o mesmo produto. Peça de chassi, marca, motor ou medida diferente não entra aqui. Nada é unido sozinho: confira no QuickBooks.")}</p>
          <ul className="et-dup">{d.duplicatas.map((g, i) => <li key={i}><Chip tone={g.motivo === 'mesmo nome' ? 'warn' : 'neutral'}>{g.motivo === 'mesmo nome' ? tr("mesmo nome") : tr("nome parecido")}</Chip>
            <ul>{g.itens.map(p => <li key={p.id}><span>{p.full_name || p.name}</span> <span className="small muted mono">#{p.id}{p.price ? ` · US$ ${p.price.toFixed(2)}` : ''}</span></li>)}</ul></li>)}</ul></>}
      </div>}
    </div>}
  </Section>
}

interface PilotoDia { chave: string; client_id: number | null; nome: string; origens: string[] }
const ORIGEM: Record<string, string> = { 'sessão': tr("sessão"), corrida: tr("corrida"), 'serviço': tr("serviço") }

/** Os pilotos de hoje (sessão do site, corrida e serviço do Asana), os mesmos do balcão do celular.
 *  Dono, 13/10: "quando eu ler, aparecer qual o piloto que tem ali no dia, para poder selecionar". */
function PilotosDoDia({ onEscolher, desativado }: { onEscolher: (id: number, nome: string) => void; desativado?: boolean }) {
  const [p, setP] = useState<PilotoDia[] | null>(null)
  useEffect(() => { api.get<{ pilotos: PilotoDia[] }>('/balcao/rapido').then(r => setP(r.pilotos.filter(x => x.client_id))).catch(() => setP([])) }, [])
  if (!p) return <span className="spin" />
  if (!p.length) return <p className="small muted" style={{ margin: 0 }}>{tr("Ninguém marcado hoje no Asana, nas sessões do site ou nas corridas.")}</p>
  return <div className="br-pilotos">{p.map(x => <button key={x.chave} className="br-piloto" disabled={desativado} onClick={() => onEscolher(x.client_id as number, x.nome)}>
    <b>{x.nome}</b><small>{x.origens.map(o => ORIGEM[o] || o).join(' · ')}</small></button>)}</div>
}

/** Peça lida sem cliente aberto: em vez de "leia primeiro o QR do cliente", pergunta de quem é. */
function DeQuemE({ item, onEscolher, onFechar }: { item: Item; onEscolher: (id: number, nome: string) => void; onFechar: () => void }) {
  return <Scrim onMouseDown={onFechar}><div className="modal stack" style={{ maxWidth: 520, gap: 12 }} onMouseDown={e => e.stopPropagation()}
    role="dialog" aria-modal="true" aria-labelledby="dqe-h">
    <h2 id="dqe-h" className="h3">{tr("De quem é?")}</h2>
    <p style={{ margin: 0 }}><b>{item.name}</b></p>
    <PilotosDoDia onEscolher={onEscolher} />
    <Picker label={tr("Outro cliente")} value={null} onPick={(c: Client | null) => { if (c) onEscolher(c.id, c.pilot_name || c.name) }} />
    <button className="btn ghost" onClick={onFechar}>{tr("Cancelar")}</button>
  </div></Scrim>
}

export function Balcao() {
  const { can } = useAuth()
  const { clientId } = useParams()
  const nav = useNavigate()
  const toast = useToast()
  const [modo, setModo] = useState<Modo>('cobrar')
  const [local, setLocal] = useState(lerLocal)
  const [texto, setTexto] = useState('')
  const [teclado, setTeclado] = useState(false)
  const [camera, setCamera] = useState(false)
  const [est, setEst] = useState<Estado | null>(null)
  const [novo, setNovo] = useState<string | null>(null)
  const [semQbo, setSemQbo] = useState<Item | null>(null)
  const [abrindo, setAbrindo] = useState(false)
  // voltou do parts pelo "voltar" (página guardada pelo navegador): o botão volta a funcionar
  useEffect(() => {
    const f = (e: PageTransitionEvent) => { if (e.persisted) { setAbrindo(false); restaurarReferrer() } }
    window.addEventListener('pageshow', f)
    return () => window.removeEventListener('pageshow', f)
  }, [])
  async function abrirCelular() {
    if (abrindo) return
    setAbrindo(true)
    try {
      const r = await pedirPasse()
      if (r.acao && r.passe) { irComPasse(r.acao, r.passe); return }
      setAbrindo(false); nav('/balcao/rapido')
    } catch (e) { setAbrindo(false); toast((e as ApiError).message, 'crit') }
  }
  const [doCliente, setDoCliente] = useState<{ item: Item; codigo: string; msg: string } | null>(null)
  const [semCliente, setSemCliente] = useState<{ item: Item; codigo: string } | null>(null)
  const [indo, setIndo] = useState(false)
  const campo = useRef<HTMLInputElement>(null)
  const cid = clientId ? Number(clientId) : null

  const carregar = useCallback(() => {
    if (!cid) { setEst(null); return }
    api.get<Estado>(`/balcao/cliente/${cid}`).then(setEst).catch(e => toast((e as ApiError).message, 'crit'))
  }, [cid, toast])
  useEffect(() => { carregar() }, [carregar])
  const focar = () => setTimeout(() => campo.current?.focus(), 30)
  useEffect(() => { focar() }, [cid, modo])

  async function lancar(item: Item, codigo: string, m: string, confirmado = false) {
    if (!cid) return
    setIndo(true)
    try {
      const r = await api.post<Estado>('/balcao/lancar', { client_id: cid, item_id: item.id, modo: m, codigo, local, confirmado })
      setEst(e => e ? { ...e, ...r } : e); vibrar(40)
      toast(`${item.name}: ${MODO_TXT[m]}.`, 'ok')
    } catch (e) {
      const er = e as ApiError
      vibrar(250)
      if (er.motivo === 'tem_do_cliente') setDoCliente({ item, codigo, msg: er.message })
      else if (er.motivo === 'precisa_item_qbo' && est?.gerente) setSemQbo(item)
      else toast(er.message, 'crit')
    } finally { setIndo(false); focar() }
  }

  const ler = useCallback(async (bruto: string) => {
    const t = bruto.trim()
    setTexto(''); setCamera(false)
    if (!t) return
    try {
      const r = await api.get<Lido>(`/balcao/ler${qs({ codigo: t, client_id: cid })}`)
      if (r.tipo === 'cliente') { vibrar(40); nav(`/balcao/${r.cliente.id}`); return }
      if (r.tipo === 'desconhecido') { setNovo(r.codigo); return }
      if (!cid) { vibrar(40); setSemCliente({ item: r.item, codigo: r.codigo }); return }
      await lancar(r.item, r.codigo, modo === 'cobrar' ? 'cobrar' : 'guardar')
    } catch (e) { toast((e as ApiError).message, 'crit'); vibrar(250) } finally { focar() }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cid, modo, local, est?.gerente])

  async function paraOCliente(id: number, nome: string) {
    const lido = semCliente
    setSemCliente(null)
    if (!lido) return
    try {
      await api.post('/balcao/lancar', { client_id: id, item_id: lido.item.id, modo, codigo: lido.codigo, local })
      vibrar(40); toast(`${lido.item.name} → ${nome}: ${MODO_TXT[modo]}.`, 'ok')
    } catch (e) { vibrar(250); toast((e as ApiError).message, 'crit') }
    nav(`/balcao/${id}`)
  }

  async function desfazer(l: Leitura) {
    try { const r = await api.post<Estado>(`/balcao/leituras/${l.id}/desfazer`); setEst(e => e ? { ...e, ...r } : e); toast(tr("Desfeito."), 'ok') }
    catch (e) { toast((e as ApiError).message, 'crit') }
  }

  const guardar = modo === 'guardar'
  return <div className={`stack balcao ${guardar ? 'modo-guardar' : 'modo-cobrar'}`} style={{ gap: 14 }}>
    <PageHeader title={tr("Balcão")} help={tr("Leia o QR do cliente e depois cada peça. Cobrar: a peça entra na invoice de peças do dia (não é enviada sozinha). Guardar: vai para o estoque do cliente, sem cobrar.")}>
      <button type="button" className="btn primary" onClick={abrirCelular} disabled={abrindo} aria-busy={abrindo}>
        {abrindo ? tr("Abrindo o balcão…") : tr("Abrir o balcão do celular")}</button></PageHeader>
    <div className="balcao-modos" role="radiogroup" aria-label={tr("O que fazer com a peça lida")}>
      <button role="radio" aria-checked={!guardar} className="balcao-modo cobrar" onClick={() => setModo('cobrar')}>{tr("COBRAR")}<small>{tr("entra na invoice")}</small></button>
      <button role="radio" aria-checked={guardar} className="balcao-modo guardar" onClick={() => setModo('guardar')}>{tr("GUARDAR")}<small>{tr("estoque do cliente")}</small></button>
    </div>
    <div className={`balcao-aviso ${guardar ? 'guardar' : 'cobrar'}`} role="status">
      {guardar ? tr("Modo GUARDAR: a peça vai para o estoque do cliente e NÃO é cobrada.") : tr("Modo COBRAR: cada peça lida entra na invoice de peças de hoje.")}
    </div>
    <form className="balcao-leitor" onSubmit={e => { e.preventDefault(); ler(texto) }}>
      <label className="fld grow"><span>{cid ? tr("Leia a peça (ou outro cliente)") : tr("Leia o QR do cliente")}</span>
        <input ref={campo} value={texto} onChange={e => setTexto(e.target.value)} autoComplete="off" autoCapitalize="off" spellCheck={false}
          inputMode={teclado ? 'text' : 'none'} enterKeyHint="go" disabled={indo} aria-describedby="balcao-dica" /></label>
      <div className="row wrap" style={{ gap: 8 }}>
        <button type="button" className="btn primary" onClick={() => setCamera(true)}>{tr("Ler com a câmera")}</button>
        <button type="button" className="btn sm ghost" onClick={() => { setTeclado(x => !x); focar() }}>{teclado ? tr("Esconder teclado") : tr("Digitar")}</button>
        <select aria-label={tr("Onde a peça está")} value={local} onChange={e => { setLocal(e.target.value); try { localStorage.setItem('balcao.local', e.target.value) } catch { /* sem armazenamento */ } }}>
          {LOCAIS.map(([k, r]) => <option key={k} value={k}>{r}</option>)}</select>
      </div>
      <p id="balcao-dica" className="small muted" style={{ margin: 0 }}>{tr("O leitor digita aqui sozinho. Se o campo perder o foco, toque nele.")}</p>
    </form>

    {cid && !est && <span className="spin" />}
    {est && <>
      <div className="card card-b row wrap" style={{ gap: 10 }}>
        <div className="grow"><h2 className="h2" style={{ margin: 0 }}>{est.cliente.nome}</h2>
          {est.cliente.responsavel !== est.cliente.nome && <div className="small muted">{tr("Responsável:")} {est.cliente.responsavel}</div>}</div>
        <Link className="btn sm ghost" to={`/clients/${est.cliente.id}`}>{tr("Card")}</Link>
        <button className="btn sm ghost" onClick={() => nav('/balcao')}>{tr("Trocar cliente")}</button>
      </div>
      {est.guardado.length > 0 && <Banner tone="warn">{tr("Guardado deste cliente com a gente:")} {est.guardado.map(g => `${g.name} (${g.qty} · ${g.local})`).join(', ')}{tr(". Não cobre o que é dele.")}</Banner>}
      <Section title={tr("Invoice de peças")}>
        {!est.invoices.length ? <p className="small muted" style={{ margin: 0 }}>{tr("Nenhuma peça cobrada hoje.")}</p>
          : <div className="stack" style={{ gap: 10 }}>{est.invoices.map(p => <CartaoInvoice key={p.id} p={p} gerente={est.gerente} onMudou={carregar} />)}</div>}
      </Section>
      <Section title={tr("Leituras")} count={est.leituras.length}>
        {!est.leituras.length ? <p className="small muted" style={{ margin: 0 }}>{tr("Nada lido ainda.")}</p>
          : <div className="card"><div className="tbl">{est.leituras.map(l => <div className="tr" key={l.id}>
            <span className="grow">{l.name} <span className="small muted">{tr("×")} {l.qty} · {MODO_TXT[l.mode]}</span></span>
            {l.undone_at ? <Chip tone="neutral">{tr("desfeita")}</Chip> : l.travada ? <Chip tone="neutral" title={tr("A invoice já foi enviada ou paga: ajuste pelo QuickBooks.")}>{tr("na invoice fechada")}</Chip>
              : <button className="btn sm ghost" onClick={() => desfazer(l)}>{tr("Desfazer")}</button>}
          </div>)}</div></div>}
      </Section>
    </>}
    {!cid && <Section title={tr("Abrir um cliente")}>
      <p className="small muted" style={{ marginTop: 0 }}>{tr("Os pilotos de hoje, ou escolha o cliente pelo nome.")}</p>
      <PilotosDoDia onEscolher={id => nav(`/balcao/${id}`)} />
      <Picker label={tr("Cliente")} value={null} onPick={(c: Client | null) => { if (c) nav(`/balcao/${c.id}`) }} />
    </Section>}
    {!cid && can('MANAGER') && <Revisao />}
    {!cid && <ContarEstoque />}
    {!cid && can('MANAGER') && <EtiquetasPrateleira />}
    {!cid && <AEnviar />}

    {semCliente && <DeQuemE item={semCliente.item} onEscolher={paraOCliente} onFechar={() => { setSemCliente(null); focar() }} />}
    {camera && <Camera onLer={ler} onFechar={() => { setCamera(false); focar() }} />}
    {novo && <CodigoNovo codigo={novo} gerente={!!est?.gerente} onFechar={() => { setNovo(null); focar() }}
      onFeito={i => { const c = novo; setNovo(null); if (cid && c) lancar(i, c, guardar ? 'guardar' : 'cobrar') }} />}
    {semQbo && <ItemQbo item={semQbo} onFechar={() => setSemQbo(null)} onFeito={() => setSemQbo(null)} />}
    {doCliente && <Scrim onMouseDown={() => setDoCliente(null)}><div className="modal stack" style={{ maxWidth: 480, gap: 12 }} onMouseDown={e => e.stopPropagation()}>
      <h2 className="h3">{tr("Esta peça é do cliente?")}</h2>
      <p style={{ margin: 0 }}>{doCliente.msg}</p>
      <div className="stack" style={{ gap: 8 }}>
        <button className="btn balcao-btn-guardar" onClick={() => { const d = doCliente; setDoCliente(null); lancar(d.item, d.codigo, 'usar_do_cliente') }}>{tr("Usar a dele (sem cobrar)")}</button>
        <button className="btn" onClick={() => { const d = doCliente; setDoCliente(null); lancar(d.item, d.codigo, 'cobrar', true) }}>{tr("Cobrar uma nova")}</button>
        <button className="btn ghost" onClick={() => setDoCliente(null)}>{tr("Cancelar")}</button></div>
    </div></Scrim>}
  </div>
}

/** O QR lido pela câmera de um celular qualquer abre /ops/c/<código>: vai para o card. */
export function PeloQr() {
  const { codigo } = useParams()
  const nav = useNavigate()
  const [erro, setErro] = useState<string | null>(null)
  useEffect(() => {
    api.get<Cliente>(`/balcao/c/${encodeURIComponent(codigo || '')}`).then(c => nav(`/clients/${c.id}`, { replace: true }))
      .catch(e => setErro((e as ApiError).message))
  }, [codigo, nav])
  return <><PageHeader title={tr("Cliente pelo QR")} />{erro ? <Banner tone="crit">{erro}</Banner> : <span className="spin" />}</>
}
