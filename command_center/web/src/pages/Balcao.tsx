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
import { Banner, Chip, Empty, PageHeader, Scrim, Section } from '../components/ui'
import { FotoPeca } from '../components/FotoPeca'
import { useToast } from '../components/Toast'
import { tr } from '../i18n'
import { novoDetector, temCamera, vibrar } from '../components/Leitor'
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
interface Leitura { id: number; name: string; mode: string; qty: number; at: string; undone_at: string | null; por: string | null }
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
          navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } })])
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

/** Peça sem item no QuickBooks: o gerente escolhe a categoria e cria. */
function ItemQbo({ item, onFeito, onFechar }: { item: Item; onFeito: () => void; onFechar: () => void }) {
  const toast = useToast()
  const [cats, setCats] = useState<{ id: string; nome: string }[]>([])
  const [cat, setCat] = useState('')
  const [preco, setPreco] = useState(item.price != null ? String(item.price) : '')
  const [indo, setIndo] = useState(false)
  useEffect(() => {
    api.get<{ categorias: { id: string; nome: string }[]; conectado: boolean }>('/balcao/categorias')
      .then(r => { setCats(r.categorias); if (!r.conectado) toast(tr("QuickBooks não está conectado: não dá para criar o item agora."), 'crit') })
      .catch(e => toast((e as ApiError).message, 'crit'))
  }, [toast])
  async function criar() {
    setIndo(true)
    try { await api.post(`/balcao/itens/${item.id}/quickbooks`, { categoria_id: cat, price: preco ? Number(preco) : null }); toast(tr("Item criado no QuickBooks."), 'ok'); onFeito() }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setIndo(false) }
  }
  return <Scrim onMouseDown={onFechar}><div className="modal stack" style={{ maxWidth: 480, gap: 12 }} onMouseDown={e => e.stopPropagation()}>
    <h2 className="h3">{item.name} {tr("no QuickBooks")}</h2>
    <label className="fld"><span>{tr("Preço final (US$)")}</span><input inputMode="decimal" value={preco} onChange={e => setPreco(e.target.value)} /></label>
    <label className="fld"><span>{tr("Categoria")}</span><select value={cat} onChange={e => setCat(e.target.value)}><option value="">—</option>{cats.map(c => <option key={c.id} value={c.id}>{c.nome}</option>)}</select></label>
    <div className="row" style={{ justifyContent: 'flex-end' }}><button className="btn" onClick={onFechar}>{tr("Cancelar")}</button>
      <button className="btn primary" disabled={indo || !cat || !preco} onClick={criar}>{indo ? <span className="spin" /> : tr("Criar item")}</button></div>
  </div></Scrim>
}

/* Cartão no balcão (06/10, desligado até CC_BALCAO_CARTAO=1): o cartão passa no QuickBooks
 * GoPayment, no leitor Bluetooth, em "Invoice payment" → cliente → esta invoice → Charge. O
 * GoPayment paga a PRÓPRIA invoice no QuickBooks (nada em dobro) e o número do cartão nunca
 * passa pelo Command Center. Aqui: o que procurar no app, o botão que abre o app e a conferência. */
const GOPAYMENT = 'intent://#Intent;package=com.intuit.intuitgopayment;S.browser_fallback_url='
  + encodeURIComponent('https://play.google.com/store/apps/details?id=com.intuit.intuitgopayment') + ';end'

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
      <li>{tr("Abra o QuickBooks GoPayment (botão abaixo).")}</li>
      <li>{tr("Toque em")} <b>+</b> {tr("e escolha")} <b>{tr("Invoice payment")}</b>.</li>
      <li>{tr("Procure")} <b>{p.cliente || tr("o cliente")}</b> {tr("e escolha a invoice")} <b>{p.doc_number || tr("de peças de hoje")}</b> {tr("de")} <b>{usd(p.total)}</b>.</li>
      <li>{tr("Toque em")} <b>{tr("Charge")}</b> {tr("e passe o cartão no leitor (chip ou aproximação).")}</li>
      <li>{tr("Volte aqui e toque em")} <b>{tr("Já passei o cartão")}</b>.</li>
    </ol>
    {saldo !== null && <Banner tone="warn">{tr("O QuickBooks ainda mostra saldo de")} {usd(saldo)} {tr("nesta invoice. Confira no GoPayment se a cobrança foi aprovada e tente de novo.")}</Banner>}
    <div className="row wrap" style={{ gap: 8, justifyContent: 'flex-end' }}>
      <button className="btn" onClick={onFechar}>{tr("Fechar")}</button>
      <a className="btn" href={GOPAYMENT}>{tr("Abrir o GoPayment")}</a>
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
  const carregar = useCallback(() => { api.get<{ itens: InvPecas[]; total: number }>('/balcao/invoices').then(setD).catch(() => setD({ itens: [], total: 0 })) }, [])
  useEffect(() => { carregar() }, [carregar])
  return <Section title={tr("Invoices de peças para enviar")} count={d?.total}>
    {!d ? <span className="spin" /> : !d.itens.length ? <Empty title={tr("Nada para enviar")}>{tr("As invoices de peças abertas aparecem aqui até alguém enviar.")}</Empty>
      : <div className="stack" style={{ gap: 10 }}>{d.itens.map(p => <CartaoInvoice key={p.id} p={p} gerente={can('MANAGER')} onMudou={carregar} />)}</div>}
  </Section>
}

/* #180: o que o mecânico leu no celular (peça → piloto do dia) espera aqui. O gerente confirma
 * — aí sim entra no estoque e na invoice de peças do dia da leitura — ou descarta. */
interface Pend { id: number; code: string; peca: string | null; pilot_name: string | null; client_id: number | null
  service_date: string; at: string; por: string | null
  item?: { id: number; name: string; price: number | null; qbo_item_id: string | null; do_cliente: number } }

function ItemRevisao({ p, onMudou }: { p: Pend; onMudou: (r: { itens: Pend[]; total: number }) => void }) {
  const toast = useToast()
  const [cliente, setCliente] = useState<Client | null>(null)
  const [item, setItem] = useState<Item | null>(null)
  const [novo, setNovo] = useState(false)
  const [doCliente, setDoCliente] = useState<string | null>(null)
  const [indo, setIndo] = useState(false)
  const temItem = !!(p.item || item)
  const temCliente = !!(p.client_id || cliente)
  async function confirmar(modo: string, confirmado = false) {
    setIndo(true)
    try {
      const r = await api.post<{ itens: Pend[]; total: number }>(`/balcao/revisao/${p.id}/confirmar`,
        { modo, client_id: cliente?.id ?? null, item_id: item?.id ?? null, confirmado })
      toast(tr("Peça confirmada: {0}.", MODO_TXT[modo]), 'ok'); onMudou(r)
    } catch (e) {
      const er = e as ApiError
      if (er.motivo === 'tem_do_cliente') setDoCliente(er.message); else toast(er.message, 'crit')
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
    </div>
    {!p.client_id && <Picker label={tr("Cliente desta peça")} value={cliente} onPick={setCliente} />}
    {!temItem && <button className="btn sm" onClick={() => setNovo(true)}>{tr("Dizer que peça é")}</button>}
    {doCliente && <Banner tone="warn">{doCliente}</Banner>}
    <div className="row wrap" style={{ gap: 8 }}>
      <button className="btn sm primary" disabled={indo || !temItem || !temCliente} onClick={() => confirmar('cobrar', !!doCliente)}>{doCliente ? tr("Cobrar mesmo assim") : tr("Cobrar")}</button>
      <button className="btn sm balcao-btn-guardar" disabled={indo || !temItem || !temCliente} onClick={() => confirmar('guardar')}>{tr("Guardar para o cliente")}</button>
      {(doCliente || (p.item?.do_cliente ?? 0) > 0) && <button className="btn sm" disabled={indo} onClick={() => confirmar('usar_do_cliente')}>{tr("Usar a do cliente")}</button>}
      <button className="btn sm ghost" disabled={indo} onClick={descartar}>{tr("Descartar")}</button>
    </div>
    {novo && <CodigoNovo codigo={p.code} gerente onFechar={() => setNovo(false)} onFeito={i => { setNovo(false); setItem(i) }} />}
  </div>
}

function Revisao() {
  const [d, setD] = useState<{ itens: Pend[]; total: number } | null>(null)
  useEffect(() => { api.get<{ itens: Pend[]; total: number }>('/balcao/revisao').then(setD).catch(() => setD({ itens: [], total: 0 })) }, [])
  return <Section title={tr("Revisão: lidas no celular")} count={d?.total}>
    {!d ? <span className="spin" /> : !d.itens.length ? <Empty title={tr("Nada para revisar")}>{tr("O que o mecânico registra no celular aparece aqui para você confirmar.")}</Empty>
      : <div className="stack" style={{ gap: 10 }}>{d.itens.map(p => <ItemRevisao key={p.id} p={p} onMudou={setD} />)}</div>}
  </Section>
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
  const [doCliente, setDoCliente] = useState<{ item: Item; codigo: string; msg: string } | null>(null)
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
      if (!cid) { toast(tr("Leia primeiro o QR do cliente."), 'crit'); vibrar(250); return }
      await lancar(r.item, r.codigo, modo === 'cobrar' ? 'cobrar' : 'guardar')
    } catch (e) { toast((e as ApiError).message, 'crit'); vibrar(250) } finally { focar() }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cid, modo, local, est?.gerente])

  async function desfazer(l: Leitura) {
    try { const r = await api.post<Estado>(`/balcao/leituras/${l.id}/desfazer`); setEst(e => e ? { ...e, ...r } : e); toast(tr("Desfeito."), 'ok') }
    catch (e) { toast((e as ApiError).message, 'crit') }
  }

  const guardar = modo === 'guardar'
  return <div className={`stack balcao ${guardar ? 'modo-guardar' : 'modo-cobrar'}`} style={{ gap: 14 }}>
    <PageHeader title={tr("Balcão")} help={tr("Leia o QR do cliente e depois cada peça. Cobrar: a peça entra na invoice de peças do dia (não é enviada sozinha). Guardar: vai para o estoque do cliente, sem cobrar.")}>
      <Link className="btn primary" to="/balcao/rapido">{tr("Abrir o balcão do celular")}</Link></PageHeader>
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
            {l.undone_at ? <Chip tone="neutral">{tr("desfeita")}</Chip> : <button className="btn sm ghost" onClick={() => desfazer(l)}>{tr("Desfazer")}</button>}
          </div>)}</div></div>}
      </Section>
    </>}
    {!cid && can('MANAGER') && <Revisao />}
    {!cid && <AEnviar />}

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
