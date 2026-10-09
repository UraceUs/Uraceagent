/* Suits · Alpha Line (#153): pedidos de macacão do contato à entrega.
 *
 * Dono, 08/10: "na aba de suítes ... registrar novo pedido ... Sempre dê a oportunidade ali de
 * eu adicionar uma nota, às vezes um screenshot para IA poder entender, já avançar com aquilo ali
 * no status que estiver" e "O envio ao Usman ... tem um padrão de envio. Salva esse padrão como
 * template". O que vivia no projeto SUITS do Asana (pedidos, leads e fornecedores) vem para cá.
 */
import { useMemo, useState } from 'react'
import { Link, NavLink, useNavigate, useParams } from 'react-router-dom'
import { api, ApiError, qs } from '../api/client'
import { useGet, usePaginado } from '../api/hooks'
import type { Client } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { Chip, Empty, ErrorState, Loading, PageHeader, Scrim, Section } from '../components/ui'
import { Icon } from '../components/Icon'
import { Md } from '../components/Md'
import { useToast } from '../components/Toast'
import { Picker } from '../components/Unir'
import { tr, LOCALE } from '../i18n'

interface Etapa { codigo: string; nome: string; descricao: string }
interface Medida { chave: string; numero: string; nome: string; tipo: 'comp' | 'peso' | 'texto' }
interface Campo { chave: string; nome: string }
interface Meta { etapas: Etapa[]; medidas: Medida[]; design: Campo[] }
interface Linha { id: number; title: string; product: string; quantity: number; customer_name: string | null; driver_name: string | null
  status: string; closed: number; order_date: string | null; due_on: string | null; source: string; fornecedor: string | null
  notas: number; ultima_nota: string | null; updated_at: string | null; created_at: string }
interface Nota { id: number; status: string | null; kind: string; text: string | null; tem_imagem: number; command_id: number | null
  created_at: string; autor: string | null; ia?: { status: string; output: string | null; error: string | null } | null }
type Valor = { v: number; u: string } | { t: string }
interface PedidoApi extends Omit<Linha, 'notas'> { customer_email: string | null; customer_phone: string | null; ship_address: string | null
  language: string | null; supplier_id: number | null; fornecedor_email: string | null; paid_at: string | null; tracking: string | null
  asana_gid: string | null; asana_notes: string | null; asana_status: string | null; measurements: Record<string, Valor>
  site_order: string | null; gmail_thread_cliente: string | null; gmail_thread_designer: string | null; gmail_thread_fornecedor: string | null
  medidas_texto: Record<string, string>; faltam_medidas: string[]; design: Record<string, string>; criado_por: string | null; notas: Nota[]
  client_id: number | null; cliente_nome: string | null; cliente_piloto: string | null }
/** O que o cadastro já sabe do cliente (#158: inserção manual sempre com "vincular ao cliente"). */
interface DadosCliente { client_id: number; customer_name: string | null; customer_email: string | null; customer_phone: string | null
  driver_name: string | null; ship_address: string | null; medidas: { valores: Record<string, number>; unidade: string; unidade_peso: string } | null
  de_onde: { card: boolean; conta_do_site: boolean; piloto: string | null } }
const puxarCliente = (id: number) => api.get<DadosCliente>(`/suits/cliente/${id}`)
function oQuePuxou(d: DadosCliente) {
  const itens = ['nome', d.customer_email && 'e-mail', d.customer_phone && 'telefone', d.driver_name && 'piloto',
    d.ship_address && tr("endereço da conta do site"), d.medidas && `${Object.keys(d.medidas.valores).length} medida(s) do piloto ${d.de_onde.piloto || ''}`.trim()]
  return 'Puxado do cadastro: ' + itens.filter(Boolean).join(', ') + '.'
}
const cartao = (id: number, nome: string | null, piloto: string | null) => ({ id, name: nome || '', pilot_name: piloto, email: null, phone: null } as unknown as Client)
interface Resumo { por_etapa: Record<string, number>; abertos: number; fechados: number; leads: number; fornecedores: number }
interface Lead { id: number; name: string; email: string | null; phone: string | null; notes: string | null; status: string; order_id: number | null; created_at: string; client_id: number | null }
interface Fornecedor { id: number; name: string; contact: string | null; email: string | null; phone: string | null; has_fia: number | null
  status: string | null; price: string | null; shipping: string | null; payment: string | null; lead_time: string | null; comments: string | null
  is_current: number; pedidos: number; asana_gid: string | null }
interface Email { para: string | null; assunto: string; corpo: string; faltam: string[]; fornecedor: Fornecedor | null }
interface PonteCfg { ponte_ligada: string; envio_automatico: string; designer_nome: string; designer_email: string; assinatura: string; boas_vindas: string; politica: string }
interface Ponte { config: PonteCfg; manual: boolean; motor: string; ultima_rodada: { at: string; detail: string } | null }
interface Anexo { nome: string; bytes: number }

const TOM: Record<string, 'neutral' | 'warn' | 'info' | 'accent' | 'ok' | 'crit'> = {
  standby: 'neutral', awaiting_measurements: 'warn', design_pending: 'info', design_review: 'warn', approved: 'accent',
  sent_to_supplier: 'info', in_production: 'info', in_transit: 'accent', delivered: 'ok', canceled: 'neutral' }
const IDIOMAS: [string, string][] = [['en', tr("Inglês")], ['pt', tr("Português")], ['es', tr("Espanhol")], ['it', tr("Italiano")], ['fr', tr("Francês")], ['de', tr("Alemão")]]
const KIND: Record<string, string> = { nota: tr("nota"), etapa: tr("etapa"), ia: 'IA', email: tr("e-mail") }
const horaFL = (iso: string) => { const d = new Date(iso.endsWith('Z') || iso.includes('+') ? iso : iso + 'Z'); return isNaN(d.getTime()) ? iso
  : d.toLocaleString(LOCALE(), { timeZone: 'America/New_York', day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' }).replace(',', '') }
const dia = (iso: string | null) => iso ? `${iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(2, 4)}` : '—'

function useMeta() { return useGet<Meta>('/suits/etapas') }
function nomeEtapa(meta: Meta | null, c: string) { return meta?.etapas.find(e => e.codigo === c)?.nome || c }
function EtapaChip({ meta, s }: { meta: Meta | null; s: string }) { return <Chip tone={TOM[s] || 'neutral'}>{nomeEtapa(meta, s)}</Chip> }

/* ============================================================ a aba */
const ABAS: [string, string][] = [['', tr("Pedidos")], ['leads', tr("Leads")], ['fornecedores', tr("Fornecedores")], ['ponte', tr("Ponte de e-mail")], ['modelo', tr("E-mail ao fornecedor")]]

export function Suits() {
  const { aba = '' } = useParams()
  const { can } = useAuth()
  const toast = useToast()
  const nav = useNavigate()
  const meta = useMeta()
  const resumo = useGet<Resumo>('/suits/resumo')
  const [novo, setNovo] = useState(false)
  const [importando, setImportando] = useState(false)

  async function importar() {
    setImportando(true)
    try {
      const r = await api.post<{ pedidos: number; leads: number; fornecedores: number; ja_tinha: number }>('/suits/importar')
      toast(tr("Do Asana: {0} pedido(s), {1} lead(s) e {2} fornecedor(es) novos; {3} já estavam aqui.", r.pedidos, r.leads, r.fornecedores, r.ja_tinha), 'ok')
      resumo.reload(); nav('/suits')
    } catch (e) { toast((e as ApiError).message, 'crit') } finally { setImportando(false) }
  }

  return <>
    <PageHeader title={tr("Suits · Alpha Line")} eyebrow={tr("Macacões sob medida")}
      help={<>{tr("Cada pedido de macacão, do contato à entrega, nas dez etapas. Em qualquer etapa dá para escrever uma nota, anexar um print e pedir à IA para seguir dali. O pedido ao fornecedor sai no padrão salvo em \"E-mail ao fornecedor\".")}</>}>
      {can('MANAGER') && <button className="btn ghost" disabled={importando} onClick={importar}>{importando ? tr("Importando…") : tr("Importar do Asana")}</button>}
      {can('OPERATOR') && <button className="btn primary" onClick={() => setNovo(true)}><Icon name="plus" size={16} /> {tr("Registrar novo pedido")}</button>}
    </PageHeader>
    <nav className="tabs" aria-label={tr("Suits")}>{ABAS.map(([path, rot]) => <NavLink key={path} to={path ? `/suits/${path}` : '/suits'} end
      className={() => (aba === path ? 'on' : '')}>{rot}{path === 'leads' && resumo.data ? <span className="count">{tr("&nbsp;")}{resumo.data.leads}</span> : null}</NavLink>)}</nav>
    {meta.error ? <div className="card"><ErrorState error={meta.error} retry={meta.reload} /></div>
      : aba === 'leads' ? <Leads />
      : aba === 'fornecedores' ? <Fornecedores />
      : aba === 'modelo' ? <Modelo />
      : aba === 'ponte' ? <Ponte />
      : <Pedidos meta={meta.data} resumo={resumo.data} />}
    {novo && <NovoPedido meta={meta.data} onClose={() => setNovo(false)} onDone={id => nav(`/suits/${id}`)} />}
  </>
}

function Pedidos({ meta, resumo }: { meta: Meta | null; resumo: Resumo | null }) {
  const [estado, setEstado] = useState<'abertos' | 'fechados'>('abertos')
  const [etapa, setEtapa] = useState('')
  const [busca, setBusca] = useState('')
  const base = `/suits${qs({ estado, status: etapa || undefined, q: busca.trim() || undefined })}`
  const { itens, total, erro, carregando, mais, temMais, recarregar } = usePaginado<Linha>(base, 50)
  return <Section title={estado === 'abertos' ? tr("Em andamento") : tr("Histórico")} count={total}
    right={<div className="tabs"><button className={estado === 'abertos' ? 'on' : ''} onClick={() => { setEstado('abertos'); setEtapa('') }}>{tr("Em andamento")}</button>
      <button className={estado === 'fechados' ? 'on' : ''} onClick={() => { setEstado('fechados'); setEtapa('') }}>{tr("Histórico")}</button></div>}>
    {estado === 'abertos' && meta && <div className="suit-filtro" role="group" aria-label={tr("Filtrar por etapa")}>
      <button className={`btn sm${etapa ? ' ghost' : ' on'}`} onClick={() => setEtapa('')}>{tr("Todas ·")} {resumo?.abertos ?? '…'}</button>
      {meta.etapas.filter(e => !['delivered', 'canceled'].includes(e.codigo)).map(e =>
        <button key={e.codigo} className={`btn sm${etapa === e.codigo ? ' on' : ' ghost'}`} onClick={() => setEtapa(e.codigo)} title={e.descricao}>
          {e.nome} · {resumo?.por_etapa[e.codigo] || 0}</button>)}
    </div>}
    <label className="fld"><span className="sr-only">{tr("Buscar")}</span><input value={busca} onChange={e => setBusca(e.target.value)} placeholder={tr("Buscar por cliente, piloto ou e-mail")} /></label>
    {erro ? <ErrorState error={erro} retry={recarregar} /> : carregando && !itens.length ? <Loading />
      : !itens.length ? <Empty title={estado === 'abertos' ? tr("Nenhum pedido em andamento") : tr("Nada no histórico")}>{tr("Registre um pedido novo ou importe o que está no Asana.")}</Empty>
      : <ul className="suit-lista">{itens.map(p => <li key={p.id}><Link to={`/suits/${p.id}`} className="suit-linha">
          <div className="grow" style={{ minWidth: 0 }}><b className="truncate">{p.title}</b>
            <div className="small muted truncate">{[p.product !== 'Suit' ? p.product : null, p.quantity > 1 ? `${p.quantity} un.` : null,
              p.fornecedor, p.order_date ? `pedido ${dia(p.order_date)}` : null, p.source === 'asana' ? 'do Asana' : p.source === 'ia' ? 'pela IA' : null].filter(Boolean).join(' · ')}</div></div>
          <EtapaChip meta={meta} s={p.status} />
          {p.notas > 0 && <span className="small muted" title={tr("notas")}>{p.notas} ✎</span>}
        </Link></li>)}</ul>}
    {temMais && <button className="btn ghost" disabled={carregando} onClick={mais}>{tr("Carregar mais")}</button>}
  </Section>
}

/* ============================================================ registrar */
function NovoPedido({ meta, onClose, onDone }: { meta: Meta | null; onClose: () => void; onDone: (id: number) => void }) {
  const toast = useToast()
  const forn = useGet<Fornecedor[]>('/suits/fornecedores')
  const [f, setF] = useState<Record<string, string>>({ language: 'en', product: 'Suit', quantity: '1' })
  const [design, setDesign] = useState<Record<string, string>>({})
  const [indo, setIndo] = useState(false)
  const [cli, setCli] = useState<Client | null>(null)
  const [puxado, setPuxado] = useState<DadosCliente | null>(null)
  const set = (k: string) => (e: { target: { value: string } }) => setF(x => ({ ...x, [k]: e.target.value }))
  async function escolher(c: Client | null) {
    setCli(c); setPuxado(null)
    if (!c) return
    try {
      const d = await puxarCliente(c.id)
      setPuxado(d)
      setF(x => ({ ...x, customer_name: d.customer_name || x.customer_name || '', customer_email: d.customer_email || x.customer_email || '',
        customer_phone: d.customer_phone || x.customer_phone || '', driver_name: d.driver_name || x.driver_name || '',
        ship_address: d.ship_address || x.ship_address || '' }))
    } catch (e) { toast((e as ApiError).message, 'crit') }
  }
  async function salvar() {
    if (!(f.customer_name || '').trim()) { toast(tr("Diga o nome do cliente."), 'warn'); return }
    setIndo(true)
    try {
      const p = await api.post<{ id: number }>('/suits', { ...f, quantity: Number(f.quantity) || 1,
        supplier_id: f.supplier_id ? Number(f.supplier_id) : (forn.data || []).find(x => x.is_current)?.id ?? null,
        client_id: cli?.id ?? null, medidas: puxado?.medidas ?? undefined,
        design, nota: f.nota || null })
      toast(tr("Pedido registrado."), 'ok'); onDone(p.id); onClose()
    } catch (e) { toast((e as ApiError).message, 'crit') } finally { setIndo(false) }
  }
  return <Scrim onMouseDown={onClose}><div className="modal" style={{ maxWidth: 640 }} onMouseDown={e => e.stopPropagation()} role="dialog" aria-modal="true" aria-label={tr("Registrar novo pedido")}>
    <h3>{tr("Registrar novo pedido")}</h3>
    <Picker label={tr("Vincular ao cliente (puxa os dados do cadastro)")} value={cli} onPick={escolher} />
    {puxado && <p className="small muted" style={{ marginTop: 0 }}>{oQuePuxou(puxado)}</p>}
    <div className="suit-form">
      <label className="fld"><span>{tr("Cliente")}</span><input value={f.customer_name || ''} onChange={set('customer_name')} /></label>
      <label className="fld"><span>{tr("Piloto (se não for o cliente)")}</span><input value={f.driver_name || ''} onChange={set('driver_name')} /></label>
      <label className="fld"><span>{tr("E-mail")}</span><input type="email" value={f.customer_email || ''} onChange={set('customer_email')} /></label>
      <label className="fld"><span>{tr("Telefone")}</span><input type="tel" value={f.customer_phone || ''} onChange={set('customer_phone')} /></label>
      <label className="fld"><span>{tr("Idioma do cliente")}</span><select value={f.language} onChange={set('language')}>{IDIOMAS.map(([k, n]) => <option key={k} value={k}>{n}</option>)}</select></label>
      <label className="fld"><span>{tr("Fornecedor")}</span><select value={f.supplier_id || ''} onChange={set('supplier_id')}>
        <option value="">{tr("o atual")}{(forn.data || []).find(x => x.is_current) ? ` (${(forn.data || []).find(x => x.is_current)!.name})` : ''}</option>
        {(forn.data || []).map(x => <option key={x.id} value={x.id}>{x.name}</option>)}</select></label>
      <label className="fld"><span>{tr("Produto")}</span><select value={f.product} onChange={set('product')}>{['Suit', 'T-shirt', 'Gloves', 'Outro'].map(x => <option key={x}>{x}</option>)}</select></label>
      <label className="fld"><span>{tr("Quantidade")}</span><input type="number" min={1} max={50} inputMode="numeric" value={f.quantity} onChange={set('quantity')} /></label>
    </div>
    <label className="fld"><span>{tr("Endereço de entrega (o fornecedor manda direto)")}</span><textarea rows={2} value={f.ship_address || ''} onChange={set('ship_address')} /></label>
    {meta && <details className="suit-mais"><summary>{tr("Design (opcional agora)")}</summary><div className="suit-form">
      {meta.design.map(d => <label key={d.chave} className="fld"><span>{d.nome}</span><input value={design[d.chave] || ''} onChange={e => setDesign(x => ({ ...x, [d.chave]: e.target.value }))} /></label>)}
    </div></details>}
    <label className="fld"><span>{tr("Nota (o que já se sabe)")}</span><textarea rows={3} value={f.nota || ''} onChange={set('nota')} placeholder={tr("pagou?, prazo, de onde veio o pedido, link da conversa")} /></label>
    <div className="modal-foot"><button className="btn ghost" onClick={onClose}>{tr("Cancelar")}</button>
      <button className="btn primary" disabled={indo} onClick={salvar}>{indo ? tr("Registrando…") : tr("Registrar")}</button></div>
  </div></Scrim>
}

/* ============================================================ o pedido */
export function SuitPedido() {
  const { aba: id } = useParams()           // /suits/:aba — o número do pedido chega no mesmo segmento das abas
  const meta = useMeta()
  const p = useGet<PedidoApi>(`/suits/${id}`, 15000)
  if (p.error) return <><PageHeader title={tr("Pedido de macacão")} /><div className="card"><ErrorState error={p.error} retry={p.reload} /></div></>
  if (!p.data || !meta.data) return <><PageHeader title={tr("Pedido de macacão")} /><div className="card"><Loading /></div></>
  const d = p.data
  return <>
    <PageHeader title={d.title} eyebrow={<><Link to="/suits">{tr("Suits · Alpha Line")}</Link> {tr("· pedido #")}{d.id}{d.product !== 'Suit' ? ` · ${d.product}` : ''}</>}>
      <EtapaChip meta={meta.data} s={d.status} />
    </PageHeader>
    <Etapas meta={meta.data} atual={d.status} />
    <NovaNota meta={meta.data} pedido={d} onDone={p.reload} />
    <Cliente pedido={d} onDone={p.reload} />
    <Medidas meta={meta.data} pedido={d} onDone={p.reload} />
    <Design meta={meta.data} pedido={d} onDone={p.reload} />
    <PonteDoPedido pedido={d} onDone={p.reload} />
    <EmailFornecedor pedido={d} onDone={p.reload} />
    <Linha_do_tempo meta={meta.data} notas={d.notas} />
    {d.asana_notes || d.asana_gid ? <Section title={tr("Como estava no Asana")}>
      {d.asana_status && <p className="small muted">{tr("Status no Asana:")} {d.asana_status}</p>}
      {d.asana_notes && <pre className="suit-pre">{d.asana_notes}</pre>}
      {d.asana_gid && <a href={`https://app.asana.com/0/0/${d.asana_gid}`} target="_blank" rel="noreferrer">{tr("Abrir a tarefa no Asana ↗")}</a>}
    </Section> : null}
  </>
}

function Etapas({ meta, atual }: { meta: Meta; atual: string }) {
  const i = meta.etapas.findIndex(e => e.codigo === atual)
  return <ol className="suit-etapas" aria-label={tr("Etapas do pedido")}>{meta.etapas.map((e, k) =>
    <li key={e.codigo} className={e.codigo === atual ? 'atual' : k < i && atual !== 'canceled' ? 'feita' : ''} title={e.descricao}
      aria-current={e.codigo === atual ? 'step' : undefined}><span className="n" aria-hidden="true">{k < i && atual !== 'canceled' ? '✓' : k + 1}</span>{e.nome}</li>)}</ol>
}

function NovaNota({ meta, pedido, onDone }: { meta: Meta; pedido: PedidoApi; onDone: () => void }) {
  const toast = useToast()
  const [texto, setTexto] = useState('')
  const [etapa, setEtapa] = useState(pedido.status)
  const [arquivo, setArquivo] = useState<File | null>(null)
  const [ia, setIa] = useState(true)
  const [indo, setIndo] = useState(false)
  const previa = useMemo(() => arquivo ? URL.createObjectURL(arquivo) : null, [arquivo])
  async function salvar() {
    if (!texto.trim() && !arquivo && etapa === pedido.status) { toast(tr("Escreva a nota, anexe um print ou mude a etapa."), 'warn'); return }
    const fd = new FormData()
    fd.set('texto', texto.trim()); fd.set('status', etapa === pedido.status ? '' : etapa); fd.set('pedir_ia', String(ia && !!(texto.trim() || arquivo)))
    if (arquivo) fd.set('imagem', arquivo)
    setIndo(true)
    try {
      const r = await api.postForm<{ id: number | null; command_id: number | null }>(`/suits/${pedido.id}/notas`, fd)
      toast(r.command_id ? tr("Nota salva. A IA está lendo e segue daqui; a resposta aparece na linha do tempo.") : tr("Nota salva."), 'ok')
      setTexto(''); setArquivo(null); onDone()
    } catch (e) { toast((e as ApiError).message, 'crit') } finally { setIndo(false) }
  }
  return <Section title={tr("Nota")}>
    <label className="fld"><span className="sr-only">{tr("Nota")}</span><textarea rows={3} value={texto} onChange={e => setTexto(e.target.value)}
      placeholder={tr("O que aconteceu? Ex.: cliente aprovou o design, mandou as medidas no print, pediu outra cor…")} /></label>
    <div className="suit-nota-op">
      <label className="btn ghost suit-arquivo"><Icon name="plus" size={16} /> {arquivo ? tr("Trocar print") : tr("Anexar print")}
        <input type="file" accept="image/png,image/jpeg,image/webp" onChange={e => setArquivo(e.target.files?.[0] || null)} /></label>
      <label className="fld suit-etapa"><span>{tr("Etapa")}</span><select aria-label={tr("Etapa")} value={etapa} onChange={e => setEtapa(e.target.value)}>
        {meta.etapas.map(e => <option key={e.codigo} value={e.codigo}>{e.codigo === pedido.status ? tr("{0} (atual)", e.nome) : tr("mover para {0}", e.nome)}</option>)}</select></label>
      <label className="check suit-ia"><input type="checkbox" checked={ia} onChange={e => setIa(e.target.checked)} /> {tr("Pedir à IA para seguir daqui")}</label>
      <button className="btn primary" disabled={indo} onClick={salvar}>{indo ? tr("Salvando…") : tr("Salvar nota")}</button>
    </div>
    {previa && <img src={previa} alt={tr("Print anexado")} className="suit-previa" />}
  </Section>
}

function Cliente({ pedido, onDone }: { pedido: PedidoApi; onDone: () => void }) {
  const toast = useToast()
  const [editando, setEditando] = useState(false)
  const [f, setF] = useState<Record<string, string>>({})
  const campos: [string, string, string?][] = [['customer_name', tr("Cliente")], ['driver_name', tr("Piloto")], ['customer_email', tr("E-mail"), 'email'],
    ['customer_phone', tr("Telefone"), 'tel'], ['ship_address', tr("Endereço de entrega")], ['order_date', tr("Data do pedido"), 'date'],
    ['paid_at', tr("Pago em"), 'date'], ['due_on', tr("Prazo"), 'date'], ['tracking', tr("Rastreio")]]
  const [cli, setCli] = useState<Client | null>(null)
  const abrir = () => {
    setF(Object.fromEntries([...campos.map(([k]) => [k, String((pedido as unknown as Record<string, unknown>)[k] ?? '')]), ['language', pedido.language || 'en']]))
    setCli(pedido.client_id ? cartao(pedido.client_id, pedido.cliente_nome, pedido.cliente_piloto) : null)
    setEditando(true)
  }
  async function escolher(c: Client | null) {
    setCli(c)
    if (!c) return
    try {     // vincular puxa do cadastro o que ainda está vazio aqui; o que a equipe escreveu fica
      const d = await puxarCliente(c.id)
      setF(x => ({ ...x, customer_name: x.customer_name || d.customer_name || '', customer_email: x.customer_email || d.customer_email || '',
        customer_phone: x.customer_phone || d.customer_phone || '', driver_name: x.driver_name || d.driver_name || '',
        ship_address: x.ship_address || d.ship_address || '' }))
    } catch (e) { toast((e as ApiError).message, 'crit') }
  }
  async function salvar() {
    try { await api.patch(`/suits/${pedido.id}`, { ...f, client_id: cli ? cli.id : 0 }); toast(tr("Salvo."), 'ok'); setEditando(false); onDone() }
    catch (e) { toast((e as ApiError).message, 'crit') }
  }
  return <Section title={tr("Cliente")} right={!editando && <button className="btn sm ghost" onClick={abrir}><Icon name="pencil" size={14} /> {tr("Editar")}</button>}>
    {editando ? <>
      <Picker label={tr("Vincular ao cliente (puxa os dados do cadastro)")} value={cli} onPick={escolher} />
      <div className="suit-form">{campos.map(([k, rot, tipo]) => <label key={k} className="fld"><span>{rot}</span>
        {k === 'ship_address' ? <textarea rows={2} value={f[k]} onChange={e => setF(x => ({ ...x, [k]: e.target.value }))} />
          : <input type={tipo || 'text'} value={f[k]} onChange={e => setF(x => ({ ...x, [k]: e.target.value }))} />}</label>)}
        <label className="fld"><span>{tr("Idioma")}</span><select value={f.language} onChange={e => setF(x => ({ ...x, language: e.target.value }))}>{IDIOMAS.map(([k, n]) => <option key={k} value={k}>{n}</option>)}</select></label>
      </div>
      <div className="row gap"><button className="btn ghost" onClick={() => setEditando(false)}>{tr("Cancelar")}</button><button className="btn primary" onClick={salvar}>{tr("Salvar")}</button></div>
    </> : <dl className="suit-dl">
      <div><dt>{tr("Card do cliente")}</dt><dd>{pedido.client_id ? <Link to={`/clients/${pedido.client_id}`}>{pedido.cliente_piloto || pedido.cliente_nome || `#${pedido.client_id}`} ↗</Link>
        : <span className="muted">{tr("não vinculado — Editar para vincular")}</span>}</dd></div>
      {campos.map(([k, rot]) => { const v = (pedido as unknown as Record<string, unknown>)[k] as string | null
        return <div key={k}><dt>{rot}</dt><dd>{v ? (k.endsWith('_at') || k.endsWith('_on') || k === 'order_date' ? dia(v) : v) : <span className="muted">—</span>}</dd></div> })}
      <div><dt>{tr("Idioma")}</dt><dd>{IDIOMAS.find(([k]) => k === pedido.language)?.[1] || pedido.language || <span className="muted">—</span>}</dd></div>
      <div><dt>{tr("Fornecedor")}</dt><dd>{pedido.fornecedor || <span className="muted">{tr("o atual")}</span>}</dd></div>
    </dl>}
  </Section>
}

function Medidas({ meta, pedido, onDone }: { meta: Meta; pedido: PedidoApi; onDone: () => void }) {
  const toast = useToast()
  const [editando, setEditando] = useState(false)
  const [unidade, setUnidade] = useState<'cm' | 'in'>('cm')
  const [peso, setPeso] = useState<'kg' | 'lb'>('kg')
  const [v, setV] = useState<Record<string, string>>({})
  const abrir = () => {
    const ini: Record<string, string> = {}
    for (const [k, m] of Object.entries(pedido.measurements)) ini[k] = 't' in m ? m.t : String(m.v)
    const u = Object.values(pedido.measurements).find(m => 'u' in m && (m.u === 'cm' || m.u === 'in')) as { u: 'cm' | 'in' } | undefined
    const pu = Object.values(pedido.measurements).find(m => 'u' in m && (m.u === 'kg' || m.u === 'lb')) as { u: 'kg' | 'lb' } | undefined
    if (u) setUnidade(u.u)
    if (pu) setPeso(pu.u)
    setV(ini); setEditando(true)
  }
  async function salvar() {
    try { await api.patch(`/suits/${pedido.id}`, { medidas: { valores: v, unidade, unidade_peso: peso } }); toast(tr("Medidas salvas."), 'ok'); setEditando(false); onDone() }
    catch (e) { toast((e as ApiError).message, 'crit') }
  }
  const falta = pedido.faltam_medidas.length
  return <Section title={tr("Medidas")} count={meta.medidas.length - 1 - falta}
    right={<>{falta > 0 && <Chip tone="warn">{tr("faltam")} {falta}</Chip>}{!editando && <button className="btn sm ghost" onClick={abrir}><Icon name="pencil" size={14} /> {tr("Preencher")}</button>}</>}>
    {editando && <div className="row gap wrap" style={{ marginBottom: 10 }}>
      <div className="tabs" role="group" aria-label={tr("Unidade de comprimento")}><button className={unidade === 'cm' ? 'on' : ''} onClick={() => setUnidade('cm')}>{tr("cm")}</button><button className={unidade === 'in' ? 'on' : ''} onClick={() => setUnidade('in')}>{tr("polegadas")}</button></div>
      <div className="tabs" role="group" aria-label={tr("Unidade de peso")}><button className={peso === 'kg' ? 'on' : ''} onClick={() => setPeso('kg')}>{tr("kg")}</button><button className={peso === 'lb' ? 'on' : ''} onClick={() => setPeso('lb')}>{tr("lb")}</button></div>
    </div>}
    <div className="suit-medidas">{meta.medidas.map(m => editando
      ? <label key={m.chave} className="fld"><span>{m.numero} – {m.nome}{m.chave === 'bust' ? tr(" (só mulheres)") : ''}</span>
          <input inputMode={m.tipo === 'texto' ? 'text' : 'decimal'} value={v[m.chave] || ''} placeholder={m.tipo === 'texto' ? tr("42 EUR / 9 US") : m.tipo === 'peso' ? peso : unidade}
            onChange={e => setV(x => ({ ...x, [m.chave]: e.target.value }))} /></label>
      : (m.chave === 'bust' && !pedido.medidas_texto.bust) ? null
      : <div key={m.chave} className={`suit-med${pedido.medidas_texto[m.chave] ? '' : ' falta'}`}><span className="small muted">{m.numero} – {m.nome}</span><b>{pedido.medidas_texto[m.chave] || '—'}</b></div>)}</div>
    {editando && <div className="row gap" style={{ marginTop: 10 }}><button className="btn ghost" onClick={() => setEditando(false)}>{tr("Cancelar")}</button><button className="btn primary" onClick={salvar}>{tr("Salvar medidas")}</button></div>}
  </Section>
}

function Design({ meta, pedido, onDone }: { meta: Meta; pedido: PedidoApi; onDone: () => void }) {
  const toast = useToast()
  const [editando, setEditando] = useState(false)
  const [v, setV] = useState<Record<string, string>>({})
  async function salvar() {
    try { await api.patch(`/suits/${pedido.id}`, { design: v }); toast(tr("Design salvo."), 'ok'); setEditando(false); onDone() }
    catch (e) { toast((e as ApiError).message, 'crit') }
  }
  return <Section title={tr("Design")} right={!editando && <button className="btn sm ghost" onClick={() => { setV({ ...pedido.design }); setEditando(true) }}><Icon name="pencil" size={14} /> {tr("Editar")}</button>}>
    <p className="small muted">{tr("É só isto que vai para o designer: nunca pagamento nem contato do cliente.")}</p>
    {editando ? <><div className="suit-form">{meta.design.map(d => <label key={d.chave} className="fld"><span>{d.nome}</span>
        <input value={v[d.chave] || ''} onChange={e => setV(x => ({ ...x, [d.chave]: e.target.value }))} /></label>)}</div>
      <div className="row gap"><button className="btn ghost" onClick={() => setEditando(false)}>{tr("Cancelar")}</button><button className="btn primary" onClick={salvar}>{tr("Salvar")}</button></div></>
      : <dl className="suit-dl">{meta.design.map(d => <div key={d.chave}><dt>{d.nome}</dt><dd>{pedido.design[d.chave] || <span className="muted">—</span>}</dd></div>)}</dl>}
  </Section>
}

const gmailLink = (t: string) => `https://mail.google.com/mail/?authuser=urace@urace.us#all/${t}`
const tamanho = (b: number) => b > 1e6 ? `${(b / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(b / 1e3))} KB`

function PonteDoPedido({ pedido, onDone }: { pedido: PedidoApi; onDone: () => void }) {
  const toast = useToast()
  const anexos = useGet<Anexo[]>(`/suits/${pedido.id}/anexos?v=${pedido.notas.length}`)
  const [ed, setEd] = useState<Record<string, string> | null>(null)
  const [indo, setIndo] = useState(false)
  const papeis: [string, string][] = [['gmail_thread_cliente', tr("Conversa com o cliente")], ['gmail_thread_designer', tr("Conversa com o designer")],
    ['gmail_thread_fornecedor', tr("Conversa com o fornecedor")]]
  async function salvar() {
    try { await api.patch(`/suits/${pedido.id}`, ed); toast(tr("Conversas ligadas ao pedido."), 'ok'); setEd(null); onDone() }
    catch (e) { toast((e as ApiError).message, 'crit') }
  }
  async function simular() {
    setIndo(true)
    try { await api.post(`/suits/${pedido.id}/ponte/simular`); toast(tr("Simulando: a IA faz o próximo passo e o e-mail que ela mandaria aparece na linha do tempo. Nada sai."), 'ok'); setTimeout(onDone, 4000) }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setIndo(false) }
  }
  return <Section title={tr("Ponte de e-mail")} right={!ed && <button className="btn sm ghost" onClick={() => setEd(Object.fromEntries(papeis.map(([k]) => [k, String((pedido as unknown as Record<string, unknown>)[k] ?? '')])))}><Icon name="pencil" size={14} /> {tr("Ligar conversas")}</button>}>
    <p className="small muted">{tr("A IA lê e responde nestas conversas do Gmail: com o cliente, com o designer (sem os dados do cliente) e com o fornecedor.")}{pedido.site_order ? tr(" Pedido do site #{0}.", pedido.site_order) : ''}</p>
    {ed ? <><div className="suit-form">{papeis.map(([k, rot]) => <label key={k} className="fld"><span>{rot} {tr("(link ou id do Gmail)")}</span>
        <input value={ed[k]} onChange={e => setEd(x => ({ ...x!, [k]: e.target.value }))} placeholder={tr("cole o link da conversa")} /></label>)}</div>
      <div className="row gap"><button className="btn ghost" onClick={() => setEd(null)}>{tr("Cancelar")}</button><button className="btn primary" onClick={salvar}>{tr("Salvar")}</button></div></>
      : <dl className="suit-dl">{papeis.map(([k, rot]) => { const v = (pedido as unknown as Record<string, string | null>)[k]
        return <div key={k}><dt>{rot}</dt><dd>{v ? <a href={gmailLink(v)} target="_blank" rel="noreferrer">{tr("abrir no Gmail ↗")}</a> : <span className="muted">—</span>}</dd></div> })}</dl>}
    <h3 className="h3" style={{ marginTop: 12 }}>{tr("Arquivos do pedido")}</h3>
    {anexos.data && anexos.data.length ? <ul className="suit-lista">{anexos.data.map(a => <li key={a.nome}>
        <a className="suit-linha" href={`/ops/api/suits/${pedido.id}/anexos/${encodeURIComponent(a.nome)}`} target="_blank" rel="noreferrer">
          <span className="grow truncate">{a.nome}</span><span className="small muted">{tamanho(a.bytes)}</span></a></li>)}</ul>
      : <p className="small muted">{tr("Nada ainda. O que chegar por e-mail (medidas, inspiração, logos, arte) fica aqui.")}</p>}
    <div className="row gap wrap" style={{ marginTop: 10 }}><button className="btn" disabled={indo} onClick={simular}>{indo ? tr("Simulando…") : tr("Simular o próximo passo")}</button></div>
  </Section>
}

function Ponte() {
  const { can } = useAuth()
  const toast = useToast()
  const p = useGet<Ponte>('/suits/ponte')
  const [ed, setEd] = useState<PonteCfg | null>(null)
  const [indo, setIndo] = useState('')
  if (p.error) return <div className="card"><ErrorState error={p.error} retry={p.reload} /></div>
  if (!p.data) return <div className="card"><Loading /></div>
  const cfg = ed || p.data.config
  const gerente = can('MANAGER')
  const set = (k: keyof PonteCfg, v: string) => setEd({ ...cfg, [k]: v })
  async function salvar() {
    setIndo('salvar')
    try { await api.put('/suits/ponte', { ...cfg, ponte_ligada: cfg.ponte_ligada === '1', envio_automatico: cfg.envio_automatico === '1' }); setEd(null); p.reload(); toast(tr("Ponte salva."), 'ok') }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setIndo('') }
  }
  async function manualGmail() {
    setIndo('gmail')
    try { const r = await api.post<{ nome: string }>('/suits/ponte/manual/gmail'); p.reload(); toast(tr("Manual carregado do Gmail: {0}.", r.nome), 'ok') }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setIndo('') }
  }
  async function subirManual(f: File | undefined) {
    if (!f) return
    const fd = new FormData(); fd.set('arquivo', f)
    try { await api.postForm('/suits/ponte/manual', fd); p.reload(); toast(tr("Manual carregado."), 'ok') } catch (e) { toast((e as ApiError).message, 'crit') }
  }
  async function rodar() {
    setIndo('rodar')
    try { const r = await api.post<{ iniciada: boolean; nota: string | null }>('/suits/ponte/rodar'); toast(r.iniciada ? tr("Rodando: em instantes os pedidos mostram o que a IA fez.") : (r.nota || ''), r.iniciada ? 'ok' : 'warn') }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setIndo('') }
  }
  let ultima: Record<string, unknown> | null = null
  try { ultima = p.data.ultima_rodada ? JSON.parse(p.data.ultima_rodada.detail) : null } catch { ultima = null }
  const auto = cfg.envio_automatico === '1'
  return <>
    <Section title={tr("Ponte de e-mail")} right={gerente && <button className="btn sm" disabled={indo === 'rodar'} onClick={rodar}>{indo === 'rodar' ? tr("Rodando…") : tr("Rodar agora")}</button>}>
      <p className="small muted">{tr("Venda de macacão no site → a IA agradece, manda o manual de medidas e pede o design. O cliente responde → a IA grava as medidas e o design e passa ao designer só o design. O designer pergunta ou entrega a arte → a IA leva ao cliente sem os dados do designer. Roda a cada 15 minutos.")}</p>
      {p.data.motor !== 'sdk' && <p className="small" style={{ color: 'var(--warn)' }}>{tr("A ponte precisa da IA no motor novo: falta a chave da Anthropic no serviço.")}</p>}
      {!auto && <p className="small" style={{ color: 'var(--warn)' }}><b>{tr("Em simulação:")}</b> {tr("nada sai. O e-mail que a IA mandaria aparece na linha do tempo do pedido, para conferir.")}</p>}
      {auto && <p className="small" style={{ color: 'var(--ok)' }}><b>{tr("Envio automático ligado:")}</b> {tr("a IA manda sem esperar aprovação.")}</p>}
      <div className="suit-form">
        <label className="check suit-ia"><input type="checkbox" disabled={!gerente} checked={cfg.ponte_ligada === '1'} onChange={e => set('ponte_ligada', e.target.checked ? '1' : '0')} /> {tr("Ponte ligada")}</label>
        <label className="check suit-ia"><input type="checkbox" disabled={!gerente} checked={auto} onChange={e => set('envio_automatico', e.target.checked ? '1' : '0')} /> {tr("Envio automático (sem aprovação)")}</label>
        <label className="fld"><span>{tr("Designer (nome)")}</span><input disabled={!gerente} value={cfg.designer_nome} onChange={e => set('designer_nome', e.target.value)} placeholder={tr("Mateus")} /></label>
        <label className="fld"><span>{tr("E-mail do designer")}</span><input disabled={!gerente} type="email" value={cfg.designer_email} onChange={e => set('designer_email', e.target.value)} /></label>
      </div>
      <label className="fld"><span>{tr("Boas-vindas (referência; a IA adapta ao idioma e ao pedido)")}</span><textarea disabled={!gerente} rows={9} value={cfg.boas_vindas} onChange={e => set('boas_vindas', e.target.value)} /></label>
      <label className="fld"><span>{tr("Política dos macacões (a IA segue e explica ao cliente; conflito vem para a equipe)")}</span><textarea disabled={!gerente} rows={6} value={cfg.politica} onChange={e => set('politica', e.target.value)} /></label>
      <label className="fld"><span>{tr("Assinatura")}</span><textarea disabled={!gerente} rows={5} value={cfg.assinatura} onChange={e => set('assinatura', e.target.value)} /></label>
      {gerente && ed && <div className="row gap"><button className="btn ghost" onClick={() => setEd(null)}>{tr("Cancelar")}</button><button className="btn primary" disabled={indo === 'salvar'} onClick={salvar}>{tr("Salvar")}</button></div>}
    </Section>
    <Section title={tr("Manual de medidas (PDF)")}>
      <p className="small">{p.data.manual ? <>{tr("Carregado.")} <a href="/ops/api/suits/ponte/manual" target="_blank" rel="noreferrer">{tr("Ver o PDF ↗")}</a></> : <span style={{ color: 'var(--warn)' }}>{tr("Ainda não carregado: as boas-vindas não saem sem ele.")}</span>}</p>
      {gerente && <div className="row gap wrap"><button className="btn" disabled={indo === 'gmail'} onClick={manualGmail}>{indo === 'gmail' ? tr("Buscando…") : tr("Buscar no Gmail")}</button>
        <label className="btn ghost suit-arquivo"><Icon name="plus" size={16} /> {tr("Subir o PDF")}<input type="file" accept="application/pdf" onChange={e => subirManual(e.target.files?.[0])} /></label></div>}
    </Section>
    {ultima && <Section title={tr("Última rodada")}><p className="small muted">{horaFL(p.data.ultima_rodada!.at)}</p><pre className="suit-pre">{JSON.stringify(ultima, null, 1)}</pre></Section>}
  </>
}

function EmailFornecedor({ pedido, onDone }: { pedido: PedidoApi; onDone: () => void }) {
  const toast = useToast()
  const e = useGet<Email>(`/suits/${pedido.id}/email-fornecedor?v=${pedido.updated_at || ''}`)
  const [indo, setIndo] = useState(false)
  async function rascunho() {
    setIndo(true)
    try { const r = await api.post<{ para: string }>(`/suits/${pedido.id}/email-fornecedor/rascunho`); toast(tr("Rascunho criado no Gmail para {0}. Anexe o mockup final e envie.", r.para), 'ok'); onDone() }
    catch (x) { toast((x as ApiError).message, 'crit') } finally { setIndo(false) }
  }
  return <Section title={tr("Pedido ao fornecedor")}>
    {e.error ? <ErrorState error={e.error} retry={e.reload} /> : !e.data ? <Loading rows={2} /> : <>
      {e.data.faltam.length > 0 && <p className="small" style={{ color: 'var(--warn)' }}>{tr("Falta")} {e.data.faltam.join(' e ')} {tr("para mandar ao fornecedor.")}</p>}
      <div className="small muted">{tr("Para:")} {e.data.para || '—'} {tr("· Assunto:")} <b>{e.data.assunto}</b></div>
      <pre className="suit-pre">{e.data.corpo}</pre>
      <div className="row gap wrap"><button className="btn primary" disabled={indo || e.data.faltam.length > 0} onClick={rascunho}>{indo ? tr("Criando…") : tr("Criar rascunho no Gmail")}</button>
        <Link className="btn ghost" to="/suits/modelo">{tr("Editar o modelo")}</Link></div>
    </>}
  </Section>
}

function Linha_do_tempo({ meta, notas }: { meta: Meta; notas: Nota[] }) {
  const lista = [...notas].reverse()
  return <Section title={tr("Linha do tempo")} count={notas.length}>
    {!lista.length ? <Empty title={tr("Nada ainda")} /> : <ol className="suit-tempo">{lista.map(n => <li key={n.id} className={`k-${n.kind}`}>
      <div className="small muted">{horaFL(n.created_at)} · {n.autor || (n.kind === 'ia' ? tr("IA") : tr("sistema"))} · {KIND[n.kind] || n.kind}{n.status ? ` · ${nomeEtapa(meta, n.status)}` : ''}</div>
      {n.text && <div className="suit-texto">{n.text}</div>}
      {n.tem_imagem ? <a href={`/ops/api/suits/notas/${n.id}/imagem`} target="_blank" rel="noreferrer"><img className="suit-img" loading="lazy" src={`/ops/api/suits/notas/${n.id}/imagem`} alt={tr("Print da nota")} /></a> : null}
      {n.ia && <div className="suit-ia-res">{n.ia.status === 'DONE' ? <Md text={n.ia.output || ''} /> : n.ia.status === 'FAILED'
        ? <span style={{ color: 'var(--crit)' }}>{tr("A IA não conseguiu:")} {n.ia.error}</span> : <span className="muted">{tr("A IA está trabalhando nesta nota…")}</span>}
        {n.command_id && <Link className="small" to={`/ai/${n.command_id}`}>{tr("abrir no AI Command")}</Link>}</div>}
    </li>)}</ol>}
  </Section>
}

/* ============================================================ leads */
function Leads() {
  const toast = useToast()
  const nav = useNavigate()
  const [estado, setEstado] = useState('aberto')
  const [busca, setBusca] = useState('')
  const { itens, total, erro, carregando, mais, temMais, recarregar } = usePaginado<Lead>(`/suits/leads${qs({ estado, q: busca.trim() || undefined })}`, 100)
  const [novo, setNovo] = useState<Record<string, string> | null>(null)
  const [cli, setCli] = useState<Client | null>(null)
  function escolher(c: Client | null) {
    setCli(c)
    if (c) setNovo(x => ({ ...x, name: c.pilot_name && c.pilot_name !== c.name ? `${c.pilot_name} (resp. ${c.name})` : c.name,
      email: c.email || x?.email || '', phone: c.phone || x?.phone || '' }))
  }
  async function criar() {
    try { await api.post('/suits/leads', { ...novo, client_id: cli?.id ?? null }); setNovo(null); setCli(null); recarregar(); toast(tr("Lead guardado."), 'ok') }
    catch (e) { toast((e as ApiError).message, 'crit') }
  }
  async function virar(l: Lead) {
    try { const p = await api.post<{ id: number }>(`/suits/leads/${l.id}/pedido`); nav(`/suits/${p.id}`) } catch (e) { toast((e as ApiError).message, 'crit') }
  }
  async function perdido(l: Lead) {
    try { await api.patch(`/suits/leads/${l.id}`, { status: 'perdido' }); recarregar() } catch (e) { toast((e as ApiError).message, 'crit') }
  }
  return <Section title={tr("Leads de macacão")} count={total} right={<button className="btn sm" onClick={() => setNovo({})}><Icon name="plus" size={14} /> {tr("Novo lead")}</button>}>
    <p className="small muted">{tr("Quem já demonstrou interesse: guardado para vender de novo.")}</p>
    <div className="row gap wrap"><div className="tabs">{[['aberto', tr("Abertos")], ['convertido', tr("Viraram pedido")], ['perdido', tr("Perdidos")]].map(([k, n]) =>
      <button key={k} className={estado === k ? 'on' : ''} onClick={() => setEstado(k)}>{n}</button>)}</div>
      <label className="fld grow" style={{ margin: 0 }}><span className="sr-only">{tr("Buscar")}</span><input value={busca} onChange={e => setBusca(e.target.value)} placeholder={tr("Buscar")} /></label></div>
    {novo && <div className="card-in"><Picker label={tr("Vincular ao cliente (puxa os dados do cadastro)")} value={cli} onPick={escolher} /></div>}
    {novo && <div className="suit-form card-in">
      <label className="fld"><span>{tr("Nome")}</span><input value={novo.name || ''} onChange={e => setNovo(x => ({ ...x, name: e.target.value }))} autoFocus /></label>
      <label className="fld"><span>{tr("E-mail")}</span><input value={novo.email || ''} onChange={e => setNovo(x => ({ ...x, email: e.target.value }))} /></label>
      <label className="fld"><span>{tr("Telefone")}</span><input value={novo.phone || ''} onChange={e => setNovo(x => ({ ...x, phone: e.target.value }))} /></label>
      <label className="fld"><span>{tr("Nota")}</span><input value={novo.notes || ''} onChange={e => setNovo(x => ({ ...x, notes: e.target.value }))} /></label>
      <div className="row gap"><button className="btn ghost" onClick={() => setNovo(null)}>{tr("Cancelar")}</button><button className="btn primary" onClick={criar}>{tr("Guardar")}</button></div>
    </div>}
    {erro ? <ErrorState error={erro} retry={recarregar} /> : carregando && !itens.length ? <Loading /> : !itens.length ? <Empty title={tr("Nenhum lead aqui")} />
      : <ul className="suit-lista">{itens.map(l => <li key={l.id} className="suit-linha">
          <div className="grow" style={{ minWidth: 0 }}><b>{l.name}</b>
            <div className="small muted">{[l.email, l.phone].filter(Boolean).join(' · ') || '—'}</div>
            {l.notes && <div className="small suit-texto">{l.notes}</div>}</div>
          {l.status === 'aberto' && <div className="row gap wrap"><button className="btn sm" onClick={() => virar(l)}>{tr("Virar pedido")}</button><button className="btn sm ghost" onClick={() => perdido(l)}>{tr("Perdido")}</button></div>}
          {l.client_id && <Link className="btn sm ghost" to={`/clients/${l.client_id}`}>{tr("Card do cliente")}</Link>}
          {l.order_id && <Link className="btn sm ghost" to={`/suits/${l.order_id}`}>{tr("Ver pedido")}</Link>}
        </li>)}</ul>}
    {temMais && <button className="btn ghost" disabled={carregando} onClick={mais}>{tr("Carregar mais")}</button>}
  </Section>
}

/* ============================================================ fornecedores */
const CAMPOS_FORN: [keyof Fornecedor, string][] = [['contact', tr("Contato")], ['email', tr("E-mail")], ['phone', tr("Telefone")], ['status', tr("Situação")],
  ['price', tr("Valor por macacão")], ['shipping', tr("Frete")], ['payment', tr("Pagamento")], ['lead_time', tr("Prazo")], ['comments', tr("Comentários")]]

function Fornecedores() {
  const { can } = useAuth()
  const toast = useToast()
  const lista = useGet<Fornecedor[]>('/suits/fornecedores')
  const [ed, setEd] = useState<Partial<Fornecedor> | null>(null)
  async function salvar() {
    if (!ed) return
    try {
      const corpo = { ...ed, is_current: !!ed.is_current }
      if (ed.id) await api.patch(`/suits/fornecedores/${ed.id}`, corpo); else await api.post('/suits/fornecedores', corpo)
      setEd(null); lista.reload(); toast(tr("Fornecedor salvo."), 'ok')
    } catch (e) { toast((e as ApiError).message, 'crit') }
  }
  return <Section title={tr("Fornecedores")} count={lista.data?.length} right={can('MANAGER') && <button className="btn sm" onClick={() => setEd({})}><Icon name="plus" size={14} /> {tr("Novo")}</button>}>
    {lista.error ? <ErrorState error={lista.error} retry={lista.reload} /> : !lista.data ? <Loading /> : !lista.data.length ? <Empty title={tr("Nenhum fornecedor")}>{tr("Importe do Asana ou cadastre.")}</Empty>
      : <div className="suit-forns">{lista.data.map(f => <article key={f.id} className="card suit-forn">
          <div className="row gap"><h3 className="h3 grow">{f.name}</h3>{f.is_current ? <Chip tone="ok">{tr("atual")}</Chip> : null}
            {f.has_fia === 1 ? <Chip tone="info">{tr("FIA")}</Chip> : f.has_fia === 0 ? <Chip>{tr("sem FIA")}</Chip> : null}</div>
          <dl className="suit-dl">{CAMPOS_FORN.filter(([k]) => f[k]).map(([k, rot]) => <div key={k}><dt>{rot}</dt><dd>{String(f[k])}</dd></div>)}
            <div><dt>{tr("Pedidos")}</dt><dd>{f.pedidos}</dd></div></dl>
          {can('MANAGER') && <button className="btn sm ghost" onClick={() => setEd({ ...f })}><Icon name="pencil" size={14} /> {tr("Editar")}</button>}
        </article>)}</div>}
    {ed && <Scrim onMouseDown={() => setEd(null)}><div className="modal" style={{ maxWidth: 560 }} onMouseDown={e => e.stopPropagation()} role="dialog" aria-modal="true" aria-label={tr("Fornecedor")}>
      <h3>{ed.id ? tr("Editar {0}", ed.name) : tr("Novo fornecedor")}</h3>
      <div className="suit-form"><label className="fld"><span>{tr("Nome")}</span><input value={ed.name || ''} onChange={e => setEd(x => ({ ...x, name: e.target.value }))} /></label>
        {CAMPOS_FORN.map(([k, rot]) => <label key={k} className="fld"><span>{rot}</span><input value={String(ed[k] ?? '')} onChange={e => setEd(x => ({ ...x, [k]: e.target.value }))} /></label>)}
        <label className="fld"><span>{tr("Tem FIA")}</span><select value={ed.has_fia == null ? '' : String(ed.has_fia)} onChange={e => setEd(x => ({ ...x, has_fia: e.target.value === '' ? null : Number(e.target.value) }))}>
          <option value="">{tr("não sabemos")}</option><option value="1">{tr("sim")}</option><option value="0">{tr("não")}</option></select></label></div>
      <label className="check"><input type="checkbox" checked={!!ed.is_current} onChange={e => setEd(x => ({ ...x, is_current: e.target.checked ? 1 : 0 }))} /> {tr("É o fornecedor atual (recebe os pedidos)")}</label>
      <div className="modal-foot"><button className="btn ghost" onClick={() => setEd(null)}>{tr("Cancelar")}</button><button className="btn primary" onClick={salvar}>{tr("Salvar")}</button></div>
    </div></Scrim>}
  </Section>
}

/* ============================================================ o modelo do e-mail */
function Modelo() {
  const { can } = useAuth()
  const toast = useToast()
  const m = useGet<{ subject: string; body: string; updated_at: string | null; campos: string[]; padrao: { subject: string; body: string } }>('/suits/modelo')
  const [ed, setEd] = useState<{ subject: string; body: string } | null>(null)
  async function salvar() {
    if (!ed) return
    try { await api.put('/suits/modelo', ed); setEd(null); m.reload(); toast(tr("Modelo salvo: os próximos pedidos saem assim."), 'ok') } catch (e) { toast((e as ApiError).message, 'crit') }
  }
  if (m.error) return <div className="card"><ErrorState error={m.error} retry={m.reload} /></div>
  if (!m.data) return <div className="card"><Loading /></div>
  const v = ed || m.data
  return <Section title={tr("E-mail ao fornecedor")} right={can('MANAGER') && !ed && <button className="btn sm ghost" onClick={() => setEd({ subject: m.data!.subject, body: m.data!.body })}><Icon name="pencil" size={14} /> {tr("Editar")}</button>}>
    <p className="small muted">{tr("O padrão dos últimos pedidos enviados ao Usman: assunto \"SUIT - piloto\", \"Hi Usman, We have a new order:\", as 29 medidas numeradas em cm e pés/polegadas, cor e mockup, e a assinatura da URACE. Os campos")} {m.data.campos.join(' ')} {tr("são trocados pelos dados do pedido.")}{m.data.updated_at ? tr(" Editado em {0}.", horaFL(m.data.updated_at)) : ''}</p>
    {ed ? <>
      <label className="fld"><span>{tr("Assunto")}</span><input value={ed.subject} onChange={e => setEd({ ...ed, subject: e.target.value })} /></label>
      <label className="fld"><span>{tr("Corpo")}</span><textarea rows={14} value={ed.body} onChange={e => setEd({ ...ed, body: e.target.value })} /></label>
      <div className="row gap wrap"><button className="btn ghost" onClick={() => setEd(null)}>{tr("Cancelar")}</button>
        <button className="btn ghost" onClick={() => setEd({ ...m.data!.padrao })}>{tr("Voltar ao padrão")}</button><button className="btn primary" onClick={salvar}>{tr("Salvar modelo")}</button></div>
    </> : <><div className="small muted">{tr("Assunto:")} <b>{v.subject}</b></div><pre className="suit-pre">{v.body}</pre></>}
  </Section>
}
