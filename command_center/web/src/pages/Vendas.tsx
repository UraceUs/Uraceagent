/* Vendas: o fluxo do closer (dono, 17/09 — aprovado no canvas antes de virar código).
 *
 * Oportunidade não é cliente. Uma tela por oportunidade: ficha, ações, follow-ups, e a
 * conversa com a IA ali mesmo (ditando, se quiser). "Fechar venda" abre a folha que dispara
 * tudo de uma vez — cliente, QuickBooks, waiver, Asana, Kommo — e depois vira acompanhamento,
 * com botão manual por passo e tarefas personalizadas.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { useGet } from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import { Banner, Chip, Empty, ErrorState, Loading, PageHeader, Scrim, Spinner, type Tone } from '../components/ui'
import { Icon } from '../components/Icon'
import { Mic, Ouvir, TextoComVoz } from '../components/Voz'
import { diaLocal, fmtDate, fmtDateTime, fmtTime, hojeLocal, money } from '../components/fmt'
import { usePerguntar } from '../components/Perguntar'
import { useToast } from '../components/Toast'
import { InserirNoTopo } from '../components/Inserir'
import { Cartao, CdItem, CdLista, type TomD } from '../components/Cartao'
import { Picker } from '../components/Unir'
import { ESTADO_PEDIDO, tomDoPedido } from '../components/pedidoSite'
import { ConexaoGoogle, useStatusGoogle, type EventoGoogle } from '../components/GoogleAgenda'
import { Bolha } from './AI'
import type { AiCommand, Client } from '../api/types'
import { tr } from '../i18n'

export interface Opp {
  id: number; name: string; email: string | null; phone: string | null
  pilot_name: string | null; pilot_age: number | null
  service: string | null; service_date: string | null; service_time: string | null; amount: number | null
  stage: string; source: string | null; closer_user_id: number | null; closer_name?: string | null
  client_id: number | null; crm_lead_id: number | null
  next_at: string | null; next_what: string | null; lost_reason: string | null; notes: string | null
  closing: Fechamento | null; calls?: number; updated_at: string; created_at: string
  client_name?: string | null; client_pilot?: string | null; qbo_item_id?: string | null
  // #260: de onde o contato do site veio (utm_*, gclid, fbclid…). Nada da pessoa entra aqui.
  campaign?: Record<string, string> | null
}

/* #260: o nome de cada chave de campanha em linguagem de vendas. */
const CAMPANHA_ROTULO: Record<string, string> = {
  utm_source: 'origem', utm_medium: 'mídia', utm_campaign: 'campanha', utm_term: 'termo',
  utm_content: 'anúncio', campaign_id: 'id da campanha', adset_id: 'id do conjunto',
  gclid: 'clique do Google', fbclid: 'clique do Meta', fbp: 'navegador (Meta)', fbc: 'clique (Meta)',
  ref: 'indicação',
}

/** De onde veio o contato: o que o site gravou junto com a mensagem (#260). */
function CampanhaDoContato({ c }: { c: Record<string, string> }) {
  const linhas = Object.entries(c).filter(([, v]) => v)
  if (!linhas.length) return null
  return <div className="card card-b stack" style={{ gap: 6 }}>
    <div className="h2">{tr("De onde veio")}</div>
    <div className="small muted">{tr("O que o site gravou com a mensagem. Sem dado da pessoa.")}</div>
    {linhas.map(([k, v]) => <div key={k} className="row" style={{ gap: 8 }}>
      <span className="small muted" style={{ minWidth: 118 }}>{tr(CAMPANHA_ROTULO[k] || k)}</span>
      <span className="small truncate" style={{ minWidth: 0 }} title={v}>{v}</span>
    </div>)}
  </div>
}
interface Passo { passo: string; nome: string; ok: boolean | null; detalhe: string; client_id?: number; invoice?: string; envelope?: string; tarefa?: string; pendente?: boolean
  // #310 (A1): a invoice criada cujo envio falhou (enviado: false) sai de novo só pelo Reenviar, a mesma
  numero?: string; enviado?: boolean }
interface Fechamento {
  em: string; por: string; na_tabela: boolean | null; aprovado?: boolean; motivo_preco?: string; passos?: Passo[]
  // #204: a cobrança — o preço da tabela vem do catálogo; fora dela, a invoice espera o gerente
  valor?: number | null; preco_tabela?: number | null; invoice_pendente?: boolean; deposito?: number
  deposito_cobrado?: string | boolean | null; liberada?: { por: string; em: string; valor: number; preco_tabela: number | null } | null
  // #310: o pedido pago no site (por: 'stripe', sem passos) e a marca de quem está cobrando agora
  pedido?: number; cobrando?: { por: string; em: string; acao: string } | null
}
interface Tabela { item_id: string | null; nome: string; preco: number | null; deposito: number; fonte: string }
interface ItemCatalogo { id: string; name: string; price: number | null; deposito: number }
interface CardDoFechamento { id: number; name: string; pilot_name: string | null; outro_piloto: boolean }
interface Evento { id: number; kind: string; title: string | null; detail: unknown; at: string; actor: string | null; ok: number | null }
interface Coluna { etapa: string; nome: string; total: number; valor: number; oportunidades: Opp[] }
interface Board { colunas: Coluna[]; abertas: number; retornos_hoje: number; atrasados: number; so_minhas: boolean }
interface LinhaPedido { id: number | null; tipo: 'produto' | 'sessao'; nome: string; quantidade: number; unitario: number; deposito: number; valor: number
  data: string | null; turno: string | null; piloto: string | null; status: string | null; agendamento: number | null; card: number | null; nota: string | null; desta_venda: boolean }
/** #236: o pedido do site (carrinho no Stripe ou loja) com as linhas, no detalhe da venda. */
interface PedidoSite { id: number; tipo: 'produto' | 'carrinho'; status: string; total: number; pago: number | null; pago_em: string | null; entrega: string
  recibo_qbo: string | null; erro_qbo: string | null; atencao: string | null; linhas: LinhaPedido[]; link?: string }
/** #310: a invoice do serviço depois de fechar — enviada (não sai de novo), esperando (só o gerente ou o
 *  dono libera: fora da tabela, desligada pelo closer ou de antes de 14/10) ou livre (sai pelo passo). */
type EstadoInvoice = 'enviada' | 'esperando' | 'livre'
/** #310: a venda fechou? O fechamento de verdade tem a data ou os passos (o pedido pago no site também); só
 *  a marca de quem está fechando agora não é fechamento. */
const ehFechada = (f: Fechamento | null | undefined): f is Fechamento => !!f && !!(f.em || f.passos || f.por === 'stripe')
type Perguntar = ReturnType<typeof usePerguntar>
/** #310 (R4, A2): a tentativa anterior de cobrar esta venda não terminou (a invoice pode ter saído). O servidor
 *  recusa até alguém conferir no QuickBooks. O gerente (ou o dono) escolhe aqui: "Não saiu: mandar" repete a
 *  chamada com `confirmar`; "Saiu: registrar o número" grava a invoice que saiu, e nada é cobrado de novo
 *  (devolve 'registrada'). Quem vende vê o aviso do servidor. */
async function comConfirmacao<T>(oid: number, fn: (confirmar: boolean) => Promise<T>, gerente: boolean, perguntar: Perguntar): Promise<T | 'registrada'> {
  try { return await fn(false) } catch (e) {
    const er = e as ApiError
    if (er?.motivo !== 'tentativa_sem_desfecho' || !gerente) throw e
    const r = await perguntar({ titulo: tr("A tentativa anterior não terminou"), perigo: true, ok: tr("Não saiu: mandar"),
      alt: tr("Saiu: registrar o número"), texto: <>{er.message} <b>{tr("Confira no QuickBooks antes de escolher.")}</b></> })
    if (r === true) return await fn(true)
    if (r !== 'alt' || !await registrarQueSaiu(oid, perguntar)) throw e
    return 'registrada'
  }
}
/** #310 (A2): "A invoice saiu" — o gerente informa o número; o servidor confere no QuickBooks (só leitura) que ela
 *  existe e é deste cliente, e grava. Se o valor não bate, pergunta de novo. false: cancelou. */
async function registrarQueSaiu(oid: number, perguntar: Perguntar): Promise<boolean> {
  const numero = await perguntar({ titulo: tr("Registrar a invoice que saiu"), campo: tr("Número da invoice no QuickBooks (Invoice no.)"), ok: tr("Registrar a invoice"),
    texto: tr("O painel confere no QuickBooks que a invoice existe e é deste cliente. Nada é cobrado de novo.") })
  if (typeof numero !== 'string' || !numero.trim()) return false
  try { await api.post(`/sales/${oid}/invoice/registrar`, { numero: numero.trim() }) } catch (e) {
    const er = e as ApiError
    if (er?.motivo !== 'valor_diferente') throw e
    if (await perguntar({ titulo: tr("O valor não bate"), texto: er.message, ok: tr("Registrar mesmo assim"), perigo: true }) !== true) return false
    await api.post(`/sales/${oid}/invoice/registrar`, { numero: numero.trim(), aceitar_diferenca: true })
  }
  return true
}
const REGISTRADA = () => tr("Invoice registrada: a venda fica com a que saiu, e nada é cobrado de novo.")
interface NaoEnviada { invoice: string; numero: string; o_que: 'invoice' | 'deposito' }
interface Detalhe { oportunidade: Opp; eventos: Evento[]; pedido?: PedidoSite | null; etapas: { codigo: string; nome: string }[]; resultados: { codigo: string; nome: string }[]; tabela?: Tabela | null; pode_liberar?: boolean; card?: CardDoFechamento | null; invoice?: EstadoInvoice | null; nao_enviadas?: NaoEnviada[] }
interface Agenda { retornos: (Opp & { atrasado: boolean })[]; ligacoes_hoje: { at: string; title: string; name: string }[] }

const ETAPA_TOM: Record<string, Tone> = { NOVO: 'neutral', CONVERSA: 'info', PROPOSTA: 'warn', FECHAMENTO: 'accent', GANHO: 'ok', PERDIDO: 'crit' }
const ETAPA_PT: Record<string, string> = { NOVO: tr("Novo"), CONVERSA: tr("Em conversa"), PROPOSTA: tr("Proposta"), FECHAMENTO: tr("Fechamento"), GANHO: tr("Ganho"), PERDIDO: tr("Perdido") }
const KIND_ICONE: Record<string, string> = { call: 'phone', email: 'mail', note: 'pencil', stage: 'target', waiver: 'doc', invoice: 'dollar', asana: 'list', kommo: 'chat', client: 'people', task: 'check', next: 'clock', ia: 'spark' }
const CANAL_ICONE = (s?: string | null) => { const t = (s || '').toLowerCase(); return t.includes('insta') ? 'instagram' : t.includes('face') || t.includes('messenger') ? 'facebook' : t.includes('whats') ? 'whatsapp' : t.includes('liga') || t.includes('call') ? 'phone' : t.includes('site') || t.includes('web') ? 'globe' : 'target' }
const nomeDo = (o: Opp) => o.pilot_name && o.pilot_name !== o.name ? `${o.name} · piloto ${o.pilot_name}` : o.name
const paraInput = (iso?: string | null) => (iso ? iso.slice(0, 16) : '')
const paraISO = (local: string) => (local ? new Date(local).toISOString() : '')

// ------------------------------------------------------------------ quadro
export function Oportunidades() {
  const { can, user } = useAuth()
  const nav = useNavigate()
  // vendas é área do operador: todos veem tudo, e quem quiser filtra as suas (dono, 17/09)
  const [soMinhas, setSoMinhas] = useState(false)
  const b = useGet<Board>(`/sales/board${soMinhas ? '?minhas=1' : ''}`, 30000)
  const [nova, setNova] = useState(false)
  const [busca, setBusca] = useState('')
  if (b.loading && !b.data) return <Loading rows={5} />
  if (b.error) return <ErrorState error={b.error} retry={b.reload} />
  const d = b.data!
  const filtra = (o: Opp) => !busca || `${o.name} ${o.pilot_name || ''} ${o.email || ''} ${o.phone || ''} ${o.service || ''}`.toLowerCase().includes(busca.toLowerCase())
  return <div className="stack">
    <PageHeader title={tr("Oportunidades")} eyebrow={tr("Vendas · {0}", user?.name?.split(' ')[0] || '')}
      help={<>{tr("Quem está perto de fechar. Oportunidade não é cliente: só vira card de cliente quando a venda fecha.")}</>}>
      <div className="row" style={{ gap: 8 }}>
        <input className="input" style={{ width: 220 }} placeholder={tr("Buscar nome, telefone…")} value={busca} onChange={e => setBusca(e.target.value)} />
        <Mic valor={busca} onTexto={setBusca} titulo={tr("Ditar a busca")} />
        <button className={`btn${soMinhas ? ' on' : ''}`} onClick={() => setSoMinhas(v => !v)} title={soMinhas ? tr("Mostrando só as suas") : tr("Mostrando as de todos")}>
          <Icon name="user" size={16} /> {soMinhas ? tr("Só minhas") : tr("Todas")}
        </button>
        <Link className="btn" to="/sales/agenda"><Icon name="cal" size={16} /> {tr("Agenda")}</Link>
        {can('OPERATOR') && <button className="btn primary" onClick={() => setNova(true)}><Icon name="plus" size={16} /> {tr("Nova oportunidade")}</button>}
      </div>
    </PageHeader>

    <div className="strip">
      <div className="it"><span className="lbl">{tr("Abertas")}</span><span className="val">{d.abertas}</span></div>
      <div className="it link" onClick={() => nav('/sales/agenda')}><span className="lbl">{tr("Retornos hoje")}</span><span className="val">{d.retornos_hoje}</span></div>
      <div className="it link" onClick={() => nav('/sales/agenda')}><span className="lbl">{tr("Atrasados")}</span><span className={`val ${d.atrasados ? 'crit' : ''}`}>{d.atrasados}</span></div>
      <div className="it"><span className="lbl">{tr("Em proposta")}</span><span className="val">{money(d.colunas.find(c => c.etapa === 'PROPOSTA')?.valor || 0)}</span></div>
      <div className="it"><span className="lbl">{tr("Em fechamento")}</span><span className="val">{money(d.colunas.find(c => c.etapa === 'FECHAMENTO')?.valor || 0)}</span></div>
    </div>

    <div className="board">
      {d.colunas.map(c => <div className={`col${c.etapa === 'FECHAMENTO' ? ' today' : ''}`} key={c.etapa}>
        <div className="ch"><span className="truncate">{c.nome}</span><span className="count">{c.total}{c.valor ? ` · ${money(c.valor)}` : ''}</span></div>
        <div className="cards">
          {c.oportunidades.filter(filtra).length === 0 && <div className="small muted" style={{ padding: 8 }}>{tr("vazia")}</div>}
          {/* #313: cada oportunidade no cartão D compacto; o cartão inteiro abre a venda */}
          {c.oportunidades.filter(filtra).map(o => {
            const atrasado = !!o.next_at && o.next_at < new Date().toISOString()
            const [rot, tom]: [string, TomD] = o.stage === 'GANHO' ? [o.client_id ? tr("virou cliente") : ETAPA_PT.GANHO, 'ok'] : o.stage === 'PERDIDO' ? [ETAPA_PT.PERDIDO, 'crit']
              : o.next_at ? [atrasado ? tr("retorno atrasado") : tr("retorno marcado"), atrasado ? 'crit' : 'warn'] : [ETAPA_PT[o.stage] || o.stage, 'neutral']
            return <Cartao key={o.id} id={`opp-${o.id}`} nivel={2} mini abrir={`/sales/${o.id}`} estado={rot} tom={tom} avatar={o.name} nome={o.name}
              sub={[<span key="origem" className="row" style={{ gap: 6, justifyContent: 'center' }}><Icon name={CANAL_ICONE(o.source)} size={13} />{o.source || tr("sem origem")}
                {!!o.calls && <span>· {o.calls} {tr("ligação(ões)")}</span>}</span>,
                o.service ? `${o.service}${o.service_date ? ` · ${fmtDate(o.service_date)}` : ''}` : null]}
              grande={o.amount ? money(o.amount) : null}>
              {(o.next_at || (o.stage === 'PERDIDO' && o.lost_reason)) && <CdLista>
                {o.next_at && <CdItem tom={atrasado ? 'crit' : 'warn'} glifo="◷">{fmtDateTime(o.next_at)}{o.next_what ? ` · ${o.next_what}` : ''}</CdItem>}
                {o.stage === 'PERDIDO' && o.lost_reason && <CdItem tom="neutral">{tr("motivo:")} {o.lost_reason}</CdItem>}
              </CdLista>}
            </Cartao>
          })}
        </div>
      </div>)}
    </div>
    {nova && <NovaOportunidade onClose={() => setNova(false)} onCriada={id => { setNova(false); nav(`/sales/${id}`) }} />}
  </div>
}

function NovaOportunidade({ onClose, onCriada, lead }: { onClose: () => void; onCriada: (id: number) => void; lead?: number }) {
  const toast = useToast()
  const [f, setF] = useState({ name: '', phone: '', email: '', pilot_name: '', pilot_age: '', service: '', amount: '', source: 'Ligação', notes: '' })
  const [busy, setBusy] = useState(false)
  const [cli, setCli] = useState<Client | null>(null)
  const set = (k: keyof typeof f) => (v: string) => setF(x => ({ ...x, [k]: v }))
  // #158 (dono, 08/10): inserção manual sempre com "vincular ao cliente" — puxa o cadastro e o fechamento cai no card dele
  function escolher(c: Client | null) {
    setCli(c)
    if (c) setF(x => ({ ...x, name: c.name || x.name, phone: c.phone || x.phone, email: c.email || x.email,
      pilot_name: c.pilot_name && c.pilot_name !== c.name ? c.pilot_name : x.pilot_name }))
  }
  async function criar() {
    if (!f.name.trim()) { toast(tr("Diga o nome de quem você falou."), 'crit'); return }
    setBusy(true)
    try {
      const r = await api.post<{ id: number; ja_e_cliente?: { id: number; nome: string } }>('/sales', {
        name: f.name, phone: f.phone || undefined, email: f.email || undefined, pilot_name: f.pilot_name || undefined,
        pilot_age: f.pilot_age ? Number(f.pilot_age) : undefined, service: f.service || undefined,
        amount: f.amount ? Number(f.amount) : undefined, source: f.source, notes: f.notes || undefined, crm_lead_id: lead,
        client_id: cli?.id ?? undefined,
      })
      toast(r.ja_e_cliente ? tr("Criada. Atenção: {0} já é cliente — no fechamento o painel liga no card dele.", r.ja_e_cliente.nome) : tr("Oportunidade criada."), 'ok')
      onCriada(r.id)
    } catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(false) }
  }
  return <Scrim onMouseDown={onClose}><div className="modal" style={{ maxWidth: 640 }} onMouseDown={e => e.stopPropagation()}>
    <button className="btn ghost sm close" onClick={onClose} aria-label={tr("Fechar")} title={tr("Fechar (Esc)")}><Icon name="x" size={16} /></button>
    <div><div className="small muted cond">{tr("Vendas")}</div><h2 className="h1" style={{ fontSize: 22 }}>{tr("Nova oportunidade")}</h2>
      <div className="small muted">{tr("Durante a ligação: só o nome é obrigatório, o resto entra depois. Todo campo aceita ditado.")}</div></div>
    <Picker label={tr("Já é cliente? Vincular ao cliente (puxa os dados do cadastro)")} value={cli} onPick={escolher} />
    <div className="grid g2">
      <div className="field"><label>{tr("Quem decide (responsável)")}</label><div className="row" style={{ gap: 6 }}><input className="input" value={f.name} onChange={e => set('name')(e.target.value)} autoFocus /><Mic valor={f.name} onTexto={set('name')} /></div></div>
      <div className="field"><label>{tr("Telefone")}</label><div className="row" style={{ gap: 6 }}><input className="input" value={f.phone} onChange={e => set('phone')(e.target.value)} placeholder="+1 407…" /><Mic valor={f.phone} onTexto={set('phone')} /></div></div>
      <div className="field"><label>{tr("E-mail")}</label><div className="row" style={{ gap: 6 }}><input className="input" value={f.email} onChange={e => set('email')(e.target.value)} /><Mic valor={f.email} onTexto={t => set('email')(t.replace(/\s+/g, '').replace(/arroba/gi, '@'))} /></div></div>
      <div className="field"><label>{tr("Origem")}</label><select className="input" value={f.source} onChange={e => set('source')(e.target.value)}>{['Ligação', 'Instagram', 'Facebook', 'WhatsApp', 'Site', 'Indicação', 'Outra'].map(x => <option key={x} value={x}>{tr(x)}</option>)}</select></div>
      <div className="field"><label>{tr("Piloto (se for outra pessoa)")}</label><div className="row" style={{ gap: 6 }}><input className="input" value={f.pilot_name} onChange={e => set('pilot_name')(e.target.value)} /><Mic valor={f.pilot_name} onTexto={set('pilot_name')} /></div></div>
      <div className="field"><label>{tr("Idade do piloto")}</label><input className="input" type="number" value={f.pilot_age} onChange={e => set('pilot_age')(e.target.value)} placeholder={tr("decide a waiver")} /></div>
      <div className="field"><label>{tr("Interesse (serviço)")}</label><div className="row" style={{ gap: 6 }}><input className="input" value={f.service} onChange={e => set('service')(e.target.value)} /><Mic valor={f.service} onTexto={set('service')} /></div></div>
      <div className="field"><label>{tr("Valor estimado")}</label><input className="input" type="number" step="0.01" value={f.amount} onChange={e => set('amount')(e.target.value)} /></div>
    </div>
    <div className="field"><label>{tr("Anotação da conversa")}</label><TextoComVoz valor={f.notes} onChange={set('notes')} linhas={3} placeholder={tr("O que ele falou… (dá para ditar)")} /></div>
    <div className="row" style={{ justifyContent: 'flex-end' }}><button className="btn" onClick={onClose}>{tr("Cancelar")}</button><button className="btn primary" disabled={busy} onClick={criar}>{busy ? <Spinner /> : tr("Criar oportunidade")}</button></div>
  </div></Scrim>
}

// ------------------------------------------------------------------ uma oportunidade
export function Oportunidade() {
  const { id } = useParams()
  const oid = Number(id)
  const toast = useToast()
  const perguntar = usePerguntar()
  const { can } = useAuth()
  const d = useGet<Detalhe>(`/sales/${oid}`, 20000)
  const [aba, setAba] = useState<'tudo' | 'call' | 'note'>('tudo')
  const [fechar, setFechar] = useState(false)
  const [liberar, setLiberar] = useState(false)
  const [ligar, setLigar] = useState(false)
  const [nota, setNota] = useState('')
  const [busy, setBusy] = useState<string | null>(null)
  const o = d.data?.oportunidade

  async function acao(nome: string, fn: () => Promise<unknown>, msg: string) {
    setBusy(nome)
    try { await fn(); toast(msg, 'ok'); d.reload() } catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(null) }
  }
  async function anotar() {
    if (!nota.trim()) return
    await acao('nota', () => api.post(`/sales/${oid}/note`, { texto: nota }), 'Anotado.')
    setNota('')
  }
  async function marcarRetorno() {
    const q = await perguntar({ titulo: tr("Agendar retorno"), campo: tr("Quando (AAAA-MM-DD HH:MM)"), valor: paraInput(new Date(Date.now() + 864e5).toISOString()).replace('T', ' ') })
    if (typeof q !== 'string' || !q.trim()) return
    const iso = paraISO(q.trim().replace(' ', 'T'))
    if (!iso) { toast(tr("Data não entendida."), 'crit'); return }
    await acao('ret', () => api.post(`/sales/${oid}/next`, { quando: iso, o_que: 'retorno' }), 'Retorno marcado.')
  }
  async function perdido() {
    const m = await perguntar({ titulo: tr("Marcar como perdido"), campo: tr("Motivo (preço, distância, sem resposta…)"), perigo: true, ok: tr("Marcar perdido") })
    if (typeof m !== 'string' || !m.trim()) return
    await acao('perd', () => api.post(`/sales/${oid}/stage`, { etapa: 'PERDIDO', motivo: m }), 'Oportunidade fechada como perdida.')
  }

  if (d.loading && !d.data) return <Loading rows={6} />
  if (d.error) return <ErrorState error={d.error} retry={d.reload} />
  if (!o) return null
  const atrasado = !!o.next_at && o.next_at < new Date().toISOString()
  const evs = (d.data?.eventos || []).filter(e => aba === 'tudo' || e.kind === aba)
  const fechada = ehFechada(o.closing)
  const passos = (fechada && o.closing?.passos) || []
  const pagoNoSite = o.closing?.por === 'stripe'           // #310: o cliente já pagou no site
  const tabela = d.data?.tabela || null
  const invoice = d.data?.invoice ?? null
  // #310: esperando quem confere o valor — o fechamento de agora (`invoice_pendente`) ou o de antes de
  // 14/10 (só `pendente` no passo). Fora disso, "esperando" é a invoice desligada pelo closer fora da tabela.
  const qboPasso = passos.find(p => p.passo === 'qbo')
  const esperaAprovacao = !!o.closing?.invoice_pendente || (!!qboPasso?.pendente && qboPasso.ok !== true)
  const precoFechado = o.closing?.preco_tabela ?? tabela?.preco ?? null
  // #204: o depósito faltou (venda fechada sem a invoice dele) e o serviço pede: o operador cobra só ele
  const faltaDeposito = fechada && !pagoNoSite && !esperaAprovacao && !o.closing?.deposito_cobrado && (tabela?.deposito || 0) > 0
  async function cobrarDeposito() {
    if (!await perguntar({ titulo: tr("Cobrar só o depósito?"), texto: tr("Uma invoice com a linha Security deposit de {0}, para {1}. É o mesmo depósito da venda automática.", money(tabela?.deposito || 0), o?.email || tr("sem e-mail")), ok: tr("Cobrar o depósito") })) return
    setBusy('dep')
    try {
      const r = await comConfirmacao(oid, c => api.post(`/sales/${oid}/deposit${c ? '?confirmar=true' : ''}`), !!d.data?.pode_liberar, perguntar)
      toast(r === 'registrada' ? REGISTRADA() : tr("Depósito cobrado."), 'ok'); d.reload()
    } catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(null) }
  }
  const naoEnviadas = d.data?.nao_enviadas || []
  async function reenviar(n: NaoEnviada) {
    await acao('reenv', () => api.post(`/sales/${oid}/invoice/reenviar`, { invoice: n.invoice }), tr("Invoice nº {0} reenviada (a mesma).", n.numero))
  }
  return <div className="stack">
    <div className="row wrap" style={{ gap: 8 }}>
      <Link className="small" to="/sales">{tr("← Oportunidades")}</Link>
      <span className="grow" />
      {o.crm_lead_id && <Link className="btn sm" to={`/crm/chat/${o.crm_lead_id}`}><Icon name="chat" size={15} /> {tr("Chat")}</Link>}
      {o.client_id && <Link className="btn sm" to={`/clients/${o.client_id}`}><Icon name="people" size={15} /> {tr("Card do cliente")}</Link>}
    </div>

    <div className="c360-h">
      <div className="who">
        <div className="row wrap" style={{ gap: 10 }}>
          <h1 className="h1" style={{ fontSize: 30 }}>{o.name}</h1>
          <Chip tone={ETAPA_TOM[o.stage]}>{ETAPA_PT[o.stage]}</Chip>
          {o.source && <Chip tone="neutral"><Icon name={CANAL_ICONE(o.source)} size={13} /> {o.source}</Chip>}
          {o.closer_name && <Chip tone="outline">{tr("closer:")} {o.closer_name.split(' ')[0]}</Chip>}
        </div>
        <div className="meta">
          {o.phone && <span><span className="k">{tr("tel")}</span><a href={`tel:${o.phone.replace(/[^\d+]/g, '')}`}>{o.phone}</a></span>}
          {o.email && <span><span className="k">{tr("e-mail")}</span><a href={`mailto:${o.email}`}>{o.email}</a></span>}
          {o.pilot_name && <span><span className="k">{tr("piloto")}</span><b>{o.pilot_name}{o.pilot_age ? tr(", {0} anos", o.pilot_age) : ''}</b></span>}
          {o.service && <span><span className="k">{tr("interesse")}</span><b>{o.service}</b>{o.service_date ? ` · ${fmtDate(o.service_date)}${o.service_time ? ' ' + o.service_time : ''}` : ''}</span>}
          {o.amount !== null && <span><span className="k">{tr("valor")}</span><b>{money(o.amount)}</b></span>}
        </div>
      </div>
      <div className="c360-acts">
        {can('OPERATOR') && <button className="btn primary" onClick={() => setLigar(true)}><Icon name="phone" size={16} /> {tr("Registrar ligação")}</button>}
        {can('OPERATOR') && o.stage !== 'GANHO' && <button className="btn" onClick={() => setFechar(true)}><Icon name="check" size={16} /> {tr("Fechar venda")}</button>}
        {can('OPERATOR') && <button className="btn" disabled={busy === 'ret'} onClick={marcarRetorno}><Icon name="clock" size={16} /> {tr("Retorno")}</button>}
        {can('OPERATOR') && o.stage !== 'PERDIDO' && o.stage !== 'GANHO' && <button className="btn ghost sm" disabled={busy === 'perd'} onClick={perdido}>{tr("Perdido")}</button>}
      </div>
    </div>

    {atrasado && <Banner tone="crit"><b>{tr("Retorno atrasado:")}</b> {fmtDateTime(o.next_at)}{o.next_what ? ` — ${o.next_what}` : ''}{tr(". Ligue e registre, ou remarque.")}</Banner>}
    {!atrasado && o.next_at && <Banner tone="info"><b>{tr("Próximo passo:")}</b> {fmtDateTime(o.next_at)}{o.next_what ? ` — ${o.next_what}` : ''}</Banner>}
    {invoice === 'esperando' && <Banner tone={esperaAprovacao ? 'warn' : 'info'}><b>{esperaAprovacao ? tr("Invoice esperando o gerente conferir o valor.") : tr("Invoice desligada no fechamento, com valor fora da tabela.")}</b> {tr("Valor da venda {0} · preço da tabela {1}.", money(o.amount || 0), precoFechado != null ? money(precoFechado) : tr("sem preço de tabela"))}{' '}
      {d.data?.pode_liberar ? <button className="btn sm primary" onClick={() => setLiberar(true)}>{tr("Liberar invoice")}</button> : <span className="muted">{tr("Só o gerente ou o dono libera.")}</span>}</Banner>}
    {faltaDeposito && can('OPERATOR') && <Banner tone="info"><b>{tr("Depósito ainda não cobrado.")}</b> {tr("O serviço pede depósito de {0}.", money(tabela?.deposito || 0))}{' '}
      <button className="btn sm" disabled={busy === 'dep'} onClick={cobrarDeposito}>{busy === 'dep' ? <Spinner /> : tr("Cobrar só o depósito")}</button></Banner>}
    {naoEnviadas.map(n => <Banner key={n.invoice} tone="warn"><b>{n.o_que === 'deposito' ? tr("Invoice do depósito nº {0} criada, o envio falhou.", n.numero) : tr("Invoice nº {0} criada, o envio falhou.", n.numero)}</b> {tr("Reenviar manda a mesma invoice: não cria outra.")}{' '}
      {can('OPERATOR') && <button className="btn sm" disabled={busy === 'reenv'} onClick={() => reenviar(n)}>{busy === 'reenv' ? <Spinner /> : tr("Reenviar")}</button>}</Banner>)}
    {pagoNoSite && <Banner tone="ok"><b>{tr("Pago no site (Stripe).")}</b> {tr("O cliente já pagou: nada a cobrar pelo painel (nem invoice, nem depósito).")}</Banner>}
    {o.stage === 'GANHO' && !pagoNoSite && <Banner tone="ok"><b>{tr("Venda fechada.")}</b> {passos.filter(p => p.ok).length} {tr("de")} {passos.length} {tr("passos concluídos")}{passos.some(p => p.ok === false) ? tr(" · falta: {0}", passos.filter(p => p.ok === false).map(p => p.nome).join(', ')) : ''}. <button className="btn ghost sm" onClick={() => setFechar(true)}>{tr("ver acompanhamento")}</button></Banner>}

    <div className="grid" style={{ gridTemplateColumns: 'minmax(0,1.4fr) minmax(0,1fr)', gap: 14 }}>
      <div className="stack">
        {/* #312: a anotação fica em cima do histórico, que cresce a cada ligação e nota */}
        {can('OPERATOR') && <InserirNoTopo rotulo={tr("Anotação (interna)")} titulo={false} sempre>
          <div className="stack">
            <label className="small muted">{tr("Anotação (interna)")}</label>
            <TextoComVoz valor={nota} onChange={setNota} linhas={2} placeholder={tr("O que combinou, o que ele pediu… (Enter guarda)")} onEnter={anotar} />
            <div className="row"><button className="btn sm" disabled={busy === 'nota' || !nota.trim()} onClick={anotar}>{busy === 'nota' ? <Spinner /> : tr("Guardar anotação")}</button></div>
          </div>
        </InserirNoTopo>}
        <div className="card">
          <div className="card-h"><h2 className="h2">{tr("Histórico")}</h2><div className="tabs" style={{ marginLeft: 'auto' }}>
            {([['tudo', tr("Tudo")], ['call', tr("Ligações")], ['note', tr("Notas")]] as const).map(([k, l]) => <button key={k} className={aba === k ? 'on' : ''} onClick={() => setAba(k)}>{l}</button>)}</div></div>
          <div className="card-b tight">
            {evs.length === 0 && <div style={{ padding: 16 }}><Empty title={tr("Nada registrado ainda")}>{tr("Registre a ligação: resultado, o que ele falou e o próximo passo.")}</Empty></div>}
            {evs.map(e => <div className="fu" key={e.id} style={{ padding: '10px 16px', display: 'grid', gridTemplateColumns: '92px 20px minmax(0,1fr) auto', gap: '0 10px', borderTop: '1px solid var(--glass-line)' }}>
              <div className="mono small muted">{fmtDate(e.at)}<br />{fmtTime(e.at)}</div>
              <Icon name={KIND_ICONE[e.kind] || 'dot'} size={16} className={e.ok === 0 ? 'muted' : undefined} />
              <div style={{ minWidth: 0 }}><div style={{ fontWeight: 600 }}>{e.title}</div>
                {typeof e.detail === 'string' && e.detail && <div className="small muted" style={{ whiteSpace: 'pre-wrap' }}>{e.detail}</div>}
                {typeof e.detail === 'object' && e.detail !== null && <div className="small muted mono">{JSON.stringify(e.detail).slice(0, 180)}</div>}</div>
              <div>{e.actor === 'ia' ? <Chip tone="accent">{tr("IA")}</Chip> : e.ok === 0 ? <Chip tone="crit">{tr("não")}</Chip> : null}</div>
            </div>)}
          </div>
        </div>

      </div>

      <div className="stack">
        {d.data?.pedido && <PedidoDoSite p={d.data.pedido} />}
        <IAdaVenda o={o} onDone={() => d.reload()} />
        {o.notes && <div className="card card-b"><div className="h2" style={{ marginBottom: 6 }}>{tr("Anotações")}</div><div className="small ink2" style={{ whiteSpace: 'pre-wrap' }}>{o.notes}</div></div>}
        {o.campaign && <CampanhaDoContato c={o.campaign} />}
        <div className="card card-b stack" style={{ gap: 6 }}>
          <div className="h2">{tr("O que já saiu")}</div>
          {passos.length === 0 && <div className="small muted">{pagoNoSite ? tr("Pago no site (Stripe): nada a cobrar pelo painel.") : tr("Nada enviado ainda. No fechamento, o painel faz tudo de uma vez.")}</div>}
          {passos.map(p => <div key={p.passo} className="row" style={{ gap: 8 }}>
            <Icon name={p.ok ? 'check' : p.ok === false ? 'x' : 'clock'} size={15} className={p.ok ? undefined : 'muted'} />
            <span className="small" style={{ color: p.ok === false ? 'var(--crit)' : undefined }}>{p.nome}</span>
            <span className="small muted truncate" style={{ marginLeft: 'auto', maxWidth: 160 }}>{p.detalhe}</span>
          </div>)}
        </div>
      </div>
    </div>

    {ligar && <RegistrarLigacao o={o} resultados={d.data!.resultados} onClose={() => setLigar(false)} onOk={() => { setLigar(false); d.reload() }} onFechar={() => { setLigar(false); setFechar(true) }} />}
    {fechar && <FecharVenda o={o} tabela={tabela} card={d.data?.card || null} podeLiberar={!!d.data?.pode_liberar} invoice={invoice} onClose={() => setFechar(false)} onOk={() => { d.reload() }} />}
    {liberar && <LiberarInvoice o={o} tabela={tabela} podeLiberar={!!d.data?.pode_liberar} onClose={() => setLiberar(false)} onOk={() => { setLiberar(false); d.reload() }} />}
  </div>
}

/** A IA dentro da venda: o closer fala (ou escreve) e ela age na oportunidade dele. */
const TURNO_PT: Record<string, string> = { manha: tr("manhã"), tarde: tr("tarde"), dia: tr("dia todo") }

function PedidoDoSite({ p }: { p: PedidoSite }) {
  const toast = useToast()
  return <div className="card card-b stack" style={{ gap: 8 }}>
    <div className="row wrap" style={{ gap: 8 }}><h2 className="h2" style={{ margin: 0 }}>{tr("Pedido do site #{0}", p.id)}</h2>
      <Chip tone={tomDoPedido(p.status)}>{ESTADO_PEDIDO[p.status] || p.status}</Chip>
      {p.recibo_qbo && <Chip tone="outline">{tr("recibo {0}", p.recibo_qbo)}</Chip>}</div>
    {p.link && <div className="row wrap" style={{ gap: 8 }}>
      <a className="btn sm ghost" href={p.link} target="_blank" rel="noreferrer">{tr("Página do pedido ↗")}</a>
      <button className="btn sm ghost" onClick={() => navigator.clipboard?.writeText(p.link!).then(() => toast(tr("Link do pedido copiado: mande ao cliente."), 'ok'))}>{tr("Copiar o link")}</button></div>}
    {p.atencao && <Banner tone="crit"><b>{tr("Resolver:")}</b> {p.atencao}</Banner>}
    {p.erro_qbo && <div className="small" style={{ color: 'var(--crit)' }}>{tr("QuickBooks: {0}", p.erro_qbo)}</div>}
    {p.linhas.map((l, i) => <div key={l.id ?? i} className="stack" style={{ gap: 2, paddingTop: 6, borderTop: '1px solid var(--glass-line)', opacity: l.desta_venda ? 1 : .6 }}>
      <div className="row" style={{ gap: 8, alignItems: 'baseline' }}><span className="grow small" style={{ fontWeight: 600, minWidth: 0, overflowWrap: 'anywhere' }}>{l.nome}{l.quantidade > 1 ? ` × ${l.quantidade}` : ''}</span>
        <span className="small mono">{money(l.unitario * l.quantidade)}</span></div>
      {l.deposito > 0 && <div className="row small muted"><span className="grow">{tr("depósito de segurança (reembolsável)")}</span><span className="mono">{money(l.deposito)}</span></div>}
      {l.tipo === 'sessao' && <div className="small muted">{l.data ? fmtDate(l.data) : ''}{l.turno ? ` · ${TURNO_PT[l.turno] || l.turno}` : ''}{l.piloto ? tr(" · piloto {0}", l.piloto) : ''}
        {l.status === 'marcada' && l.agendamento ? <> · <Link to="/site/agendamentos">{tr("agendamento #{0}", l.agendamento)}</Link></> : null}
        {l.status === 'sem_vaga' ? <b style={{ color: 'var(--crit)' }}> · {tr("sem vaga")}</b> : null}</div>}
      {!l.desta_venda && <div className="small muted">{tr("em outra venda do mesmo pedido (outro card)")}</div>}
    </div>)}
    <div className="row" style={{ gap: 8, borderTop: '1px solid var(--glass-line)', paddingTop: 6 }}><b className="grow">{tr("Total")}</b><b className="mono">{money(p.pago ?? p.total)}</b></div>
  </div>
}

function IAdaVenda({ o, onDone }: { o: Opp; onDone: () => void }) {
  const toast = useToast()
  const [texto, setTexto] = useState('')
  const [cid, setCid] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const c = useGet<AiCommand>(cid ? `/ai/commands/${cid}` : null, cid ? 2500 : undefined)
  const rodando = c.data?.status === 'QUEUED' || c.data?.status === 'RUNNING'
  useEffect(() => { if (c.data && !rodando) onDone() }, [c.data?.status]) // eslint-disable-line react-hooks/exhaustive-deps
  const contexto = `[oportunidade #${o.id} — ${o.name}${o.pilot_name ? ` (piloto ${o.pilot_name})` : ''}${o.service ? `, ${o.service}` : ''}${o.amount !== null ? `, ${money(o.amount)}` : ''}, etapa ${ETAPA_PT[o.stage]}]`
  async function mandar() {
    const t = texto.trim()
    if (!t || busy) return
    setBusy(true)
    try { const r = await api.post<{ id: number }>('/ai/commands', { text: `${contexto} ${t}` }); setCid(r.id); setTexto('') }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(false) }
  }
  const sugestoes = [tr("Registre que ele pediu para ligar amanhã às 10h"), tr("Marque retorno para sexta 9h"), tr("Envie a waiver para ele"), tr("Feche essa venda"), tr("Anote: mãe decide junto")]
  return <div className="card card-b stack" style={{ gap: 8 }}>
    <div className="row" style={{ gap: 8 }}><span className="icbox red"><Icon name="spark" /></span>
      <div><div style={{ fontWeight: 600 }}>{tr("Falar com a IA")}</div><div className="xs muted">{tr("ela age nesta oportunidade: registrar, agendar, waiver, invoice, fechar")}</div></div></div>
    <TextoComVoz valor={texto} onChange={setTexto} linhas={2} placeholder={tr("Fale ou escreva… (Enter envia)")} onEnter={mandar} disabled={busy} />
    <div className="row wrap" style={{ gap: 6 }}>
      <button className="btn primary sm" disabled={busy || !texto.trim()} onClick={mandar}>{busy ? <Spinner /> : tr("Pedir à IA")}</button>
      {c.data?.output && <Ouvir texto={c.data.output} titulo={tr("Ouvir a resposta")} />}
    </div>
    <div className="sug">{sugestoes.map(s => <button key={s} onClick={() => setTexto(s)}>{s}</button>)}</div>
    {cid && c.data && <div style={{ marginTop: 4 }}><Bolha c={c.data} onChange={() => { c.reload(); onDone() }} /></div>}
  </div>
}

function RegistrarLigacao({ o, resultados, onClose, onOk, onFechar }: { o: Opp; resultados: { codigo: string; nome: string }[]; onClose: () => void; onOk: () => void; onFechar: () => void }) {
  const toast = useToast()
  const [res, setRes] = useState('pensar')
  const [minutos, setMinutos] = useState('')
  const [texto, setTexto] = useState('')
  const [quando, setQuando] = useState('')
  const [oque, setOque] = useState('')
  const [busy, setBusy] = useState(false)
  async function salvar() {
    setBusy(true)
    try {
      await api.post(`/sales/${o.id}/call`, {
        resultado: res, minutos: minutos ? Number(minutos) : undefined, texto: texto || undefined,
        proximo_em: quando ? paraISO(quando) : undefined, proximo_que: oque || undefined,
      })
      toast(tr("Ligação registrada."), 'ok')
      if (res === 'fechou') onFechar()
      else onOk()
    } catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(false) }
  }
  return <Scrim onMouseDown={onClose}><div className="modal" style={{ maxWidth: 560 }} onMouseDown={e => e.stopPropagation()}>
    <button className="btn ghost sm close" onClick={onClose} aria-label={tr("Fechar")}><Icon name="x" size={16} /></button>
    <div><div className="small muted cond">{tr("Ligação ·")} {o.name}</div><h2 className="h1" style={{ fontSize: 22 }}>{tr("Como foi?")}</h2></div>
    <div className="row wrap" style={{ gap: 6 }}>{resultados.map(r => <button key={r.codigo} className={`btn sm${res === r.codigo ? ' on' : ''}`} onClick={() => setRes(r.codigo)}>{r.nome}</button>)}</div>
    <div className="grid g2">
      <div className="field"><label>{tr("Minutos")}</label><input className="input" type="number" value={minutos} onChange={e => setMinutos(e.target.value)} /></div>
      <div className="field"><label>{tr("Retorno (opcional)")}</label><input className="input" type="datetime-local" value={quando} onChange={e => setQuando(e.target.value)} /></div>
    </div>
    {quando && <div className="field"><label>{tr("O que fazer no retorno")}</label><div className="row" style={{ gap: 6 }}><input className="input" value={oque} onChange={e => setOque(e.target.value)} placeholder={tr("confirmar sábado e fechar")} /><Mic valor={oque} onTexto={setOque} /></div></div>}
    <div className="field"><label>{tr("O que ele falou")}</label><TextoComVoz valor={texto} onChange={setTexto} linhas={3} placeholder={tr("Dite aqui em vez de digitar…")} /></div>
    {res === 'fechou' && <Banner tone="info">{tr("Ao salvar, abre a tela de fechar a venda: um botão dispara cliente, QuickBooks, waiver, Asana e Kommo.")}</Banner>}
    <div className="row" style={{ justifyContent: 'flex-end' }}><button className="btn" onClick={onClose}>{tr("Cancelar")}</button>
      <button className="btn primary" disabled={busy} onClick={salvar}>{busy ? <Spinner /> : res === 'fechou' ? tr("Registrar e fechar venda") : tr("Registrar")}</button></div>
  </div></Scrim>
}

// ------------------------------------------------------------------ fechar venda (a tela única)
interface Extra { titulo: string; onde: 'painel' | 'asana'; quando: string; notas: string }

/** O item do catálogo do QuickBooks que a venda cobra: o preço da tabela vem dele (#204). */
function EscolherItem({ valor, onEscolher, id }: { valor: string; onEscolher: (i: ItemCatalogo | null) => void; id?: string }) {
  const c = useGet<{ itens: ItemCatalogo[] }>('/sales/catalogo')
  const itens = c.data?.itens || []
  useEffect(() => { if (valor) onEscolher(itens.find(i => i.id === valor) || null) }, [c.data]) // eslint-disable-line react-hooks/exhaustive-deps
  return <select id={id} className="input" value={valor} onChange={e => onEscolher(itens.find(i => i.id === e.target.value) || null)}>
    <option value="">{c.loading && !c.data ? tr("carregando o catálogo…") : tr("— escolha o item do catálogo —")}</option>
    {itens.map(i => <option key={i.id} value={i.id}>{i.name}{i.price != null ? ` · ${money(i.price)}` : ''}</option>)}
  </select>
}

/** Liberar invoice (#204, dono, 14/10: "precisa confirmar o valor da invoice"): só gerente e dono,
 *  vendo o valor da venda contra o preço da tabela. Fica auditado.
 *  #310 (R6): `modo="mandar"` é a mesma janela para a invoice cujo serviço não tem item no catálogo: escolhido
 *  o item, no preço da tabela ela sai pelo passo (quem vende também manda); fora dele, só o gerente libera. */
function LiberarInvoice({ o, tabela, modo = 'liberar', podeLiberar = true, onClose, onOk }: { o: Opp; tabela: Tabela | null; modo?: 'liberar' | 'mandar'; podeLiberar?: boolean; onClose: () => void; onOk: (f?: Fechamento) => void }) {
  const toast = useToast()
  const perguntar = usePerguntar()
  const [busy, setBusy] = useState(false)
  const [item, setItem] = useState<ItemCatalogo | null>(null)
  const semItem = !tabela?.item_id
  const preco = item ? item.price : (o.closing?.preco_tabela ?? tabela?.preco ?? null)
  const deposito = o.closing?.deposito_cobrado ? 0 : (item ? item.deposito : (tabela?.deposito || 0))
  const valor = o.amount || 0
  const fora = preco == null || Math.abs(valor - preco) > 0.009
  const pelaLiberacao = modo === 'liberar' || fora          // fora da tabela, só pelo Liberar (gerente ou dono)
  const bloqueado = pelaLiberacao && !podeLiberar
  async function liberar() {
    setBusy(true)
    try {
      const r = await comConfirmacao(o.id, c => pelaLiberacao
        ? api.post<{ fechamento?: Fechamento }>(`/sales/${o.id}/invoice/liberar`, { valor, item_id: item?.id || undefined, confirmar: c || undefined })
        : api.post<{ fechamento?: Fechamento }>(`/sales/${o.id}/step/qbo?item_id=${encodeURIComponent(item?.id || '')}${c ? '&confirmar=true' : ''}`), podeLiberar, perguntar)
      if (r === 'registrada') { toast(REGISTRADA(), 'ok'); onOk(); return }
      toast(pelaLiberacao ? tr("Invoice liberada e enviada.") : tr("Invoice enviada pelo QuickBooks."), 'ok'); onOk(r.fechamento)
    } catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(false) }
  }
  const linha = (rotulo: string, v: string) => <div className="inset"><div className="it" style={{ padding: '10px 14px' }}><div style={{ minWidth: 0 }}><div className="s">{rotulo}</div><div className="t mono">{v}</div></div></div></div>
  return <Scrim onMouseDown={onClose}><div className="modal" style={{ maxWidth: 560 }} onMouseDown={e => e.stopPropagation()}>
    <button className="btn ghost sm close" onClick={onClose} aria-label={tr("Fechar")}><Icon name="x" size={16} /></button>
    <div><div className="small muted cond">{tr("Venda ·")} {o.name}</div><h3 className="h1" style={{ fontSize: 22 }}>{modo === 'mandar' ? tr("Mandar a invoice") : tr("Liberar invoice")}</h3>
      <div className="small muted">{modo === 'mandar' ? tr("O serviço não tem item no catálogo do QuickBooks: escolha o item. No preço da tabela, a invoice sai agora; fora dele, só o gerente ou o dono libera.")
        : tr("Confira o valor contra o preço da tabela. Ao liberar, a invoice sai para o cliente pelo QuickBooks e fica na auditoria com o seu nome.")}</div></div>
    <div className="card" style={{ padding: 0 }}>
      {linha(tr("Serviço"), o.service || '—')}
      {linha(tr("Valor da venda"), money(valor))}
      {linha(tr("Preço da tabela (catálogo)"), preco != null ? money(preco) : tr("sem preço de tabela"))}
      {preco != null && linha(tr("Diferença"), money(valor - preco))}
      {deposito > 0 && linha(tr("Depósito de segurança (na mesma invoice)"), money(deposito))}
    </div>
    {semItem && <div className="field"><label htmlFor="liberar-item">{tr("Item do catálogo (o serviço ainda não tem)")}</label><EscolherItem id="liberar-item" valor={item?.id || ''} onEscolher={setItem} /></div>}
    {modo === 'mandar' && item && bloqueado && <Banner tone="warn">{tr("Fora da tabela com este item: só o gerente ou o dono libera.")}</Banner>}
    <div className="row" style={{ justifyContent: 'flex-end' }}><button className="btn" onClick={onClose}>{tr("Cancelar")}</button>
      <button className="btn primary" disabled={busy || (semItem && !item) || bloqueado} onClick={liberar}>{busy ? <Spinner /> : pelaLiberacao ? tr("Liberar invoice de {0}", money(valor)) : tr("Mandar invoice de {0}", money(valor))}</button></div>
  </div></Scrim>
}

function FecharVenda({ o, tabela, card, podeLiberar, invoice, onClose, onOk }: { o: Opp; tabela: Tabela | null; card: CardDoFechamento | null; podeLiberar: boolean; invoice: EstadoInvoice | null; onClose: () => void; onOk: () => void }) {
  const toast = useToast()
  const perguntar = usePerguntar()
  const [f, setF] = useState({
    service: o.service || '', service_date: (o.service_date || '').slice(0, 10), service_time: o.service_time || '',
    amount: o.amount !== null ? String(o.amount) : '',
    pilot_name: o.pilot_name || '', pilot_age: o.pilot_age !== null ? String(o.pilot_age) : '',
    email: o.email || '', phone: o.phone || '', nota_cliente: '',
  })
  // #204: o preço da tabela vem do catálogo (o item do QuickBooks), nunca do valor da venda
  const [item, setItem] = useState<ItemCatalogo | null>(null)
  const [itemId, setItemId] = useState(o.qbo_item_id || tabela?.item_id || '')
  const [irmao, setIrmao] = useState(!!card?.outro_piloto)
  const [liberar, setLiberar] = useState(false)
  const [mandar, setMandar] = useState(false)               // #310 (R6): a invoice do serviço sem item no catálogo
  const [passos, setPassos] = useState<Record<string, boolean>>({ cliente: true, qbo: true, waiver: true, asana: true, kommo: !!o.crm_lead_id })
  const [extras, setExtras] = useState<Extra[]>([])
  const [busy, setBusy] = useState(false)
  // o acompanhamento segue o servidor: a resposta que acabou de chegar vale até a ficha recarregar; depois de um
  // passo, do Liberar ou de outra aba, a linha mostra o que saiu (#310)
  const [local, setLocal] = useState<{ f: Fechamento; de: Fechamento | null } | null>(null)
  const feito = local && local.de === o.closing ? local.f : ehFechada(o.closing) ? o.closing : local?.f ?? null
  const setFeito = (fe: Fechamento) => setLocal({ f: fe, de: o.closing })
  const pagoNoSite = feito?.por === 'stripe'
  const semItem = !tabela?.item_id
  const set = (k: keyof typeof f) => (v: string) => setF(x => ({ ...x, [k]: v }))
  // #310: a linha da invoice mostra Liberar também na desligada pelo closer fora da tabela e na de antes
  // de 14/10 (o servidor diz o estado; logo depois de confirmar, antes de recarregar, vale o fechamento)
  const esperando = invoice ? invoice === 'esperando' : !!feito?.invoice_pendente
  const precoTabela = item ? item.price : (itemId ? null : tabela?.preco ?? null)
  const deposito = item ? item.deposito : (itemId ? 0 : tabela?.deposito || 0)
  const fora = !!f.amount && (precoTabela == null || Math.abs(Number(f.amount) - precoTabela) > 0.009)
  function escolher(i: ItemCatalogo | null) {
    setItem(i); setItemId(i?.id || '')
    if (i && !f.service.trim()) set('service')(i.name)
  }

  async function confirmar() {
    if (!f.service.trim() || !f.amount) { toast(tr("Diga o serviço e o valor fechado."), 'crit'); return }
    setBusy(true)
    try {
      const r = await comConfirmacao(o.id, c => api.post<{ etapa: string; fechamento: Fechamento }>(`/sales/${o.id}/close`, {
        service: f.service, service_date: f.service_date || undefined, service_time: f.service_time || undefined,
        amount: Number(f.amount), item_id: itemId || undefined, irmao: card ? irmao : undefined,
        pilot_name: f.pilot_name || undefined, pilot_age: f.pilot_age ? Number(f.pilot_age) : undefined,
        email: f.email || undefined, phone: f.phone || undefined, nota_cliente: f.nota_cliente || undefined,
        passos, extras: extras.filter(e => e.titulo.trim()).map(e => ({ titulo: e.titulo, onde: e.onde, quando: e.quando || undefined, notas: e.notas || undefined })),
        confirmar: c || undefined,
      }), podeLiberar, perguntar)
      if (r === 'registrada') { toast(REGISTRADA(), 'ok'); onOk(); return }
      setFeito(r.fechamento)
      const falhou = (r.fechamento.passos || []).filter(p => p.ok === false)
      toast(falhou.length ? tr("Fechada, mas faltou: {0}", falhou.map(p => p.nome).join(', ')) : tr("Venda fechada e tudo disparado."), falhou.length ? undefined : 'ok')
      onOk()
    } catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(false) }
  }
  async function refazer(passo: string) {
    setBusy(true)
    try {
      const r = await comConfirmacao(o.id, c => api.post(`/sales/${o.id}/step/${passo}${c ? '?confirmar=true' : ''}`), podeLiberar, perguntar)
      toast(r === 'registrada' ? REGISTRADA() : tr("Feito."), 'ok'); onOk()
    } catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(false) }
  }
  // a invoice desligada no fechamento foi escolha do closer: mandar pergunta antes, como "Cobrar só o depósito"
  async function mandarDesligada() {
    if (!await perguntar({ titulo: tr("Mandar a invoice?"), ok: tr("Mandar a invoice"),
      texto: tr("A invoice foi desligada no fechamento. Ao mandar, sai uma invoice de {0} para {1} pelo QuickBooks.", money(o.amount || 0), o.email || tr("sem e-mail")) })) return
    await refazer('qbo')
  }
  async function reenviarDaLinha(p: Passo) {
    setBusy(true)
    try { await api.post(`/sales/${o.id}/invoice/reenviar`, { invoice: p.invoice }); toast(tr("Invoice nº {0} reenviada (a mesma).", p.numero || p.invoice || ''), 'ok'); onOk() }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(false) }
  }

  const LINHAS: { k: string; nome: string; o_que: string; icone: string }[] = [
    { k: 'cliente', nome: tr("Cria o card do cliente"), o_que: irmao ? tr("card próprio do irmão · mesmo responsável, e-mail e telefone") : tr("Clientes · responsável, piloto, contato e a anotação"), icone: 'people' },
    { k: 'qbo', nome: tr("Cliente no QuickBooks e invoice enviada"), o_que: fora && !podeLiberar ? tr("fora da tabela (ou sem preço de tabela): a invoice espera o gerente conferir o valor") : deposito > 0 ? tr("manda a invoice do valor fechado + o depósito de {0}", money(deposito)) : tr("cria o cliente se faltar e manda a invoice do valor fechado"), icone: 'dollar' },
    { k: 'waiver', nome: tr("Envia a waiver"), o_que: tr("DocuSign · modelo {0} · para {1}", f.pilot_age && Number(f.pilot_age) < 18 ? 'parental (piloto menor)' : 'adulto', f.email || 'sem e-mail'), icone: 'doc' },
    { k: 'asana', nome: tr("Cria a tarefa no Asana"), o_que: tr("quadro U-RACE, com a data do serviço"), icone: 'list' },
    { k: 'kommo', nome: tr("Fecha no Kommo"), o_que: o.crm_lead_id ? tr("lead do chat → Closed won") : tr("esta oportunidade não veio do chat"), icone: 'chat' },
  ]
  return <Scrim onMouseDown={onClose}><div className="modal" style={{ maxWidth: 1080 }} onMouseDown={e => e.stopPropagation()}>
    <button className="btn ghost sm close" onClick={onClose} aria-label={tr("Fechar")}><Icon name="x" size={16} /></button>
    <div className="row" style={{ gap: 12 }}>
      <span className="icbox red" style={{ width: 44, height: 44, borderRadius: 14 }}><Icon name="check" size={22} /></span>
      <div><div className="small muted cond">{tr("Fechar venda ·")} {o.name}</div><h2 className="h1" style={{ fontSize: 24 }}>{feito ? tr("Acompanhamento do fechamento") : tr("Uma tela. Confirmou, o painel faz o resto.")}</h2></div>
    </div>

    <div className="grid" style={{ gridTemplateColumns: 'minmax(0,1fr) minmax(0,1.1fr)', gap: 14 }}>
      <div className="stack">
        <div className="h2">{tr("O que foi vendido")}</div>
        <div className="field"><label>{tr("Serviço")}</label><div className="row" style={{ gap: 6 }}><input className="input" value={f.service} onChange={e => set('service')(e.target.value)} /><Mic valor={f.service} onTexto={set('service')} /></div></div>
        <div className="grid g2">
          <div className="field"><label>{tr("Data")}</label><input className="input" type="date" value={f.service_date} onChange={e => set('service_date')(e.target.value)} /></div>
          <div className="field"><label>{tr("Hora")}</label><input className="input" type="time" value={f.service_time} onChange={e => set('service_time')(e.target.value)} /></div>
        </div>
        <div className="grid g2">
          <div className="field"><label>{tr("Valor fechado")}</label><input className="input" type="number" step="0.01" value={f.amount} onChange={e => set('amount')(e.target.value)} /></div>
          <div className="field"><span className="small muted">{tr("Preço da tabela (catálogo)")}</span><div className="mono" style={{ padding: '10px 0', fontWeight: 600 }}>{precoTabela != null ? money(precoTabela) : tr("sem preço de tabela")}</div></div>
        </div>
        <div className="field"><label htmlFor="fechar-item">{tr("Item do catálogo (QuickBooks)")}</label><EscolherItem id="fechar-item" valor={itemId} onEscolher={escolher} /></div>
        {fora ? <Banner tone="warn">{podeLiberar ? tr("Valor fora da tabela (ou sem preço de tabela). Você é gerente: ao confirmar, a invoice sai com este valor.")
          : <>{tr("Valor fora da tabela (ou sem preço de tabela): a venda fecha, o resto sai, e a")} <b>{tr("invoice espera o gerente conferir o valor")}</b> {tr("(decisão do dono, 14/10).")}</>}</Banner> : null}
        {deposito > 0 && <Banner tone="info">{tr("Depósito de segurança de {0} vai na mesma invoice, como na venda automática.", money(deposito))}</Banner>}
        <div className="grid g2">
          <div className="field"><label>{tr("Piloto")}</label><div className="row" style={{ gap: 6 }}><input className="input" value={f.pilot_name} onChange={e => set('pilot_name')(e.target.value)} /><Mic valor={f.pilot_name} onTexto={set('pilot_name')} /></div></div>
          <div className="field"><label>{tr("Idade do piloto")}</label><input className="input" type="number" value={f.pilot_age} onChange={e => set('pilot_age')(e.target.value)} placeholder={tr("decide a waiver")} /></div>
        </div>
        <div className="grid g2">
          <div className="field"><label>{tr("E-mail (invoice e waiver)")}</label><div className="row" style={{ gap: 6 }}><input className="input" value={f.email} onChange={e => set('email')(e.target.value)} /><Mic valor={f.email} onTexto={t => set('email')(t.replace(/\s+/g, '').replace(/arroba/gi, '@'))} /></div></div>
          <div className="field"><label>{tr("Telefone")}</label><input className="input" value={f.phone} onChange={e => set('phone')(e.target.value)} /></div>
        </div>
        {card && !feito && <div className="card card-b stack" style={{ gap: 6 }}>
          <div className="small">{card.outro_piloto ? <><b>{tr("O card com este contato é de {0}.", card.pilot_name || card.name)}</b> {tr("Esta venda é de {0}: se for irmão, ele ganha um card próprio, com o mesmo responsável, e-mail e telefone.", f.pilot_name || '—')}</>
            : tr("Liga no card que já existe: {0}.", card.pilot_name || card.name)}</div>
          <label className="check"><input type="checkbox" checked={irmao} onChange={e => setIrmao(e.target.checked)} /> {tr("É irmão: criar o card de {0}", f.pilot_name || tr("este piloto"))}</label>
        </div>}
        <div className="field"><label>{tr("Anotação para o card do cliente")}</label><TextoComVoz valor={f.nota_cliente} onChange={set('nota_cliente')} linhas={2} placeholder={tr("Primeira vez no kart, mãe vai junto…")} /></div>
      </div>

      <div className="stack">
        <div className="h2">{feito ? tr("Como foi cada passo") : tr("O que acontece ao confirmar")}</div>
        <div className="card" style={{ padding: 0 }}>
          {LINHAS.map(l => {
            const p = feito?.passos?.find(x => x.passo === l.k)
            return <div className="inset" key={l.k}><div className="it" style={{ padding: '10px 14px' }}>
              <span className={`icbox${p?.ok ? ' ok' : p?.ok === false ? ' crit' : ''}`}><Icon name={l.icone} /></span>
              <div style={{ minWidth: 0 }}><div className="t">{l.nome}</div><div className="s">{p ? p.detalhe : l.o_que}</div></div>
              <div className="r">
                {!feito && <button className={`sw${passos[l.k] ? '' : ' off'}`} aria-label={passos[l.k] ? tr("Ligado") : tr("Desligado")} onClick={() => setPassos(x => ({ ...x, [l.k]: !x[l.k] }))} />}
                {feito && (p?.ok && l.k === 'qbo' && p.enviado === false ? <button className="btn sm" disabled={busy} onClick={() => reenviarDaLinha(p)}>{tr("reenviar")}</button>
                  : p?.ok ? <Chip tone="ok">{tr("feito")}</Chip>
                  : l.k === 'qbo' && pagoNoSite ? <Chip tone="ok">{tr("pago no site (Stripe)")}</Chip>
                  : l.k === 'qbo' && esperando ? (podeLiberar ? <button className="btn sm primary" onClick={() => setLiberar(true)}>{tr("Liberar invoice")}</button> : <Chip tone="warn">{tr("espera o gerente")}</Chip>)
                  // #310: o serviço sem item no catálogo escolhe o item na janela (R6); a invoice desligada na tabela sai daqui (R5)
                  : l.k === 'qbo' && semItem && (p?.ok === false || invoice === 'livre') ? <button className="btn sm" disabled={busy} onClick={() => setMandar(true)}>{p?.ok === false ? tr("tentar de novo") : tr("mandar a invoice")}</button>
                  : p?.ok === false ? <button className="btn sm" disabled={busy} onClick={() => refazer(l.k)}>{tr("tentar de novo")}</button>
                  : l.k === 'qbo' && invoice === 'livre' ? <button className="btn sm" disabled={busy} onClick={mandarDesligada}>{tr("mandar a invoice")}</button>
                  : <Chip tone="neutral">—</Chip>)}
              </div>
            </div></div>
          })}
        </div>

        {!feito && <div className="card card-b stack" style={{ gap: 8 }}>
          <div className="row"><b className="small">{tr("Tarefa personalizada")}</b><span className="grow" /><button className="btn ghost sm" onClick={() => setExtras(x => [...x, { titulo: '', onde: 'painel', quando: '', notas: '' }])}><Icon name="plus" size={14} /> {tr("adicionar")}</button></div>
          {extras.length === 0 && <div className="xs muted">{tr("Algo diferente para este cliente (mandar um material, avisar o instrutor, cobrar o equipamento). Vai junto no Confirmar.")}</div>}
          {extras.map((e, i) => <div className="stack" key={i} style={{ gap: 6, borderTop: i ? '1px solid var(--glass-line)' : undefined, paddingTop: i ? 8 : 0 }}>
            <div className="row" style={{ gap: 6 }}>
              <input className="input" placeholder={tr("O que fazer")} value={e.titulo} onChange={ev => setExtras(x => x.map((y, j) => j === i ? { ...y, titulo: ev.target.value } : y))} />
              <Mic valor={e.titulo} onTexto={t => setExtras(x => x.map((y, j) => j === i ? { ...y, titulo: t } : y))} />
              <button className="btn ghost sm" onClick={() => setExtras(x => x.filter((_, j) => j !== i))} aria-label={tr("Remover")}><Icon name="x" size={14} /></button>
            </div>
            <div className="row" style={{ gap: 6 }}>
              <select className="input" style={{ width: 150 }} value={e.onde} onChange={ev => setExtras(x => x.map((y, j) => j === i ? { ...y, onde: ev.target.value as 'painel' | 'asana' } : y))}>
                <option value="painel">{tr("lembrete no painel")}</option><option value="asana">{tr("tarefa no Asana")}</option>
              </select>
              <input className="input" type="date" style={{ width: 170 }} value={e.quando} onChange={ev => setExtras(x => x.map((y, j) => j === i ? { ...y, quando: ev.target.value } : y))} />
            </div>
          </div>)}
        </div>}

        {feito && (feito.passos || []).filter(p => p.passo.startsWith('extra:')).map(p => <div className="row small" key={p.passo} style={{ gap: 8 }}>
          <Icon name={p.ok ? 'check' : 'x'} size={14} /><span>{p.passo.replace('extra:', '')}</span><span className="muted">{p.detalhe}</span></div>)}

        {!feito ? <div className="row fecha-acao" style={{ gap: 8 }}>
          <button className="btn primary" style={{ flex: '1 1 auto', minHeight: 48 }} disabled={busy} onClick={confirmar}>{busy ? <Spinner /> : <><Icon name="check" size={16} /> {tr("Confirmar e fechar a venda")}</>}</button>
          <button className="btn" onClick={onClose}>{tr("Voltar")}</button>
        </div> : <div className="row" style={{ gap: 8 }}>
          <div className="small muted" style={{ flex: '1 1 auto' }}>{tr("Fechada")} {fmtDateTime(feito.em)} {tr("por")} {feito.por}{feito.motivo_preco ? ` · ${feito.motivo_preco}` : ''}</div>
          <button className="btn" onClick={onClose}>{tr("Fechar")}</button>
        </div>}
      </div>
    </div>
    {liberar && <LiberarInvoice o={o} tabela={tabela} podeLiberar={podeLiberar} onClose={() => setLiberar(false)} onOk={fe => { setLiberar(false); if (fe) setFeito(fe); onOk() }} />}
    {mandar && <LiberarInvoice o={o} tabela={tabela} modo="mandar" podeLiberar={podeLiberar} onClose={() => setMandar(false)} onOk={fe => { setMandar(false); if (fe) setFeito(fe); onOk() }} />}
  </div></Scrim>
}

// ------------------------------------------------------------------ agenda de vendas
const DIAS_GOOGLE = 7
function maisDias(dia: string, n: number) {
  const d = new Date(dia + 'T12:00:00Z'); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10)
}
/** Os dias (AAAA-MM-DD, Florida) em que um evento do Google aparece, dentro do período visto. */
function diasDoEvento(e: EventoGoogle, de: string, ate: string) {
  if (!e.dia_todo) return [diaLocal(e.inicio)]
  const out: string[] = []
  for (let d = e.inicio.slice(0, 10); d < e.fim.slice(0, 10) && out.length < 62; d = maisDias(d, 1)) if (d >= de && d <= ate) out.push(d)
  return out
}
/** O compromisso do Google que bate com o horário do retorno (só os que deixam a pessoa ocupada). */
function conflito(o: Opp, evs: EventoGoogle[]) {
  if (!o.next_at || o.next_at.length <= 10) return null
  const t = new Date(o.next_at).getTime()
  return evs.find(e => e.ocupado && !e.dia_todo && new Date(e.inicio).getTime() <= t && t < new Date(e.fim).getTime()) || null
}

export function AgendaVendas() {
  const a = useGet<Agenda>('/sales/agenda', 30000)
  const g = useStatusGoogle()
  const nav = useNavigate()
  const hoje = hojeLocal()
  const ate = maisDias(hoje, DIAS_GOOGLE)
  const ev = useGet<{ conectado: boolean; erro?: string; eventos: EventoGoogle[] }>(g.data?.conectado ? `/google/events?de=${hoje}&ate=${ate}` : null, 120000)
  const evs = useMemo(() => ev.data?.eventos || [], [ev.data])
  const por = useMemo(() => {
    const m = new Map<string, { retornos: (Opp & { atrasado: boolean })[]; google: EventoGoogle[] }>()
    const dia = (d: string) => { if (!m.has(d)) m.set(d, { retornos: [], google: [] }); return m.get(d)! }
    for (const o of a.data?.retornos || []) dia(diaLocal(o.next_at)).retornos.push(o)
    for (const e of evs) for (const d of diasDoEvento(e, hoje, ate)) dia(d).google.push(e)
    return [...m.entries()].sort((x, y) => x[0].localeCompare(y[0]))
  }, [a.data, evs, hoje, ate])
  if (a.loading && !a.data) return <Loading rows={5} />
  if (a.error) return <ErrorState error={a.error} retry={a.reload} />
  return <div className="stack">
    <PageHeader title={tr("Agenda de vendas")} eyebrow={tr("Vendas")} help={<>{tr("Os retornos que você marcou ao registrar cada ligação. Atrasado fica em vermelho e também aparece em Precisa de atenção.")} {tr("Conectando o seu Google Calendar, cada retorno seu vira evento lá e os seus compromissos do Google aparecem aqui, para ver conflito.")}</>}>
      <Link className="btn" to="/sales"><Icon name="target" size={16} /> {tr("Oportunidades")}</Link>
    </PageHeader>
    <ConexaoGoogle status={g.data} onMudou={() => { g.reload(); ev.reload() }} />
    {ev.data?.erro && <Banner tone="warn">{tr("Não deu para ler o seu Google Calendar agora: {0}", ev.data.erro)}</Banner>}
    {por.length === 0 && <Empty title={tr("Nenhum retorno marcado")}>{tr("Ao registrar uma ligação, escolha o próximo passo e a data: ele aparece aqui.")}</Empty>}
    {por.map(([dia, { retornos: lista, google }]) => <div className="card" key={dia}>
      <div className="card-h"><h2 className="h2">{dia === hoje ? tr("Hoje") : fmtDate(dia)}</h2><span className="count">{lista.length}</span></div>
      <div className="card-b tight">
        {lista.map(o => { const choque = conflito(o, google); return <div className="att" key={o.id} style={{ cursor: 'pointer' }} onClick={() => nav(`/sales/${o.id}`)}>
          <div className={`lv ${o.atrasado ? 'CRITICAL' : 'MEDIUM'}`} />
          <div className="grow">
            <div className="row wrap" style={{ gap: 8 }}><span className="mono small">{fmtTime(o.next_at)}</span><b>{nomeDo(o)}</b>
              <Chip tone={ETAPA_TOM[o.stage]}>{ETAPA_PT[o.stage]}</Chip>{o.atrasado && <Chip tone="crit">{tr("atrasado")}</Chip>}
              {choque && <Chip tone="warn" title={choque.titulo || tr("Ocupado")}>{tr("conflito no Google")}</Chip>}</div>
            <div className="small muted">{o.next_what || tr("retorno")}{o.service ? ` · ${o.service}` : ''}{o.amount ? ` · ${money(o.amount)}` : ''}{o.phone ? ` · ${o.phone}` : ''}</div>
          </div>
          <div className="row" style={{ gap: 6 }}>{o.phone && <a className="btn sm" href={`tel:${o.phone.replace(/[^\d+]/g, '')}`} onClick={e => e.stopPropagation()}><Icon name="phone" size={14} /> {tr("ligar")}</a>}</div>
        </div> })}
        {google.map(e => <div className="att google-ev" key={`g${e.id}${dia}`}>
          <div className="lv LOW" />
          <div className="grow">
            <div className="row wrap" style={{ gap: 8 }}><span className="mono small">{e.dia_todo ? tr("dia todo") : `${fmtTime(e.inicio)}–${fmtTime(e.fim)}`}</span>
              <span>{e.titulo || tr("Ocupado")}</span><Chip>{tr("Google")}</Chip>{!e.ocupado && <Chip>{tr("livre")}</Chip>}</div>
          </div>
        </div>)}
      </div>
    </div>)}
    {!!a.data?.ligacoes_hoje.length && <div className="card"><div className="card-h"><h2 className="h2">{tr("Ligações de hoje")}</h2><span className="count">{a.data.ligacoes_hoje.length}</span></div>
      <div className="card-b tight">{a.data.ligacoes_hoje.map((l, i) => <div className="att" key={i}><div className="lv LOW" /><div className="grow">
        <div className="row" style={{ gap: 8 }}><span className="mono small">{fmtTime(l.at)}</span><b>{l.name}</b></div><div className="small muted">{l.title}</div></div></div>)}</div></div>}
  </div>
}

/** Botão "Passar para vendas" usado no chat do Kommo. */
/* Dono, 06/10: "eu continuo ali no chat, mas quando eu clico ele registra no painel de vendas
 * aquele lead como uma oportunidade. Caso não tenha, ele cria. Se já tiver, aponta uma nova."
 * Executa e fica no chat: nada de abrir a página de vendas. */
export function PassarParaVendas({ leadId }: { leadId: number }) {
  const toast = useToast()
  const { can } = useAuth()
  const [busy, setBusy] = useState(false)
  const [feito, setFeito] = useState<number | null>(null)
  const ref = useRef(false)
  if (!can('OPERATOR')) return null
  return <button className="btn sm" disabled={busy} title={tr("Registra este lead como oportunidade no painel de vendas, sem sair do chat")} onClick={async () => {
    if (ref.current) return
    ref.current = true; setBusy(true)
    try {
      const r = await api.post<{ id: number; reaproveitada: boolean; nova: boolean; do_lead: number }>(`/sales/from-lead/${leadId}`)
      toast(r.reaproveitada ? tr("Já registrado agora há pouco no painel de vendas.")
        : r.do_lead > 1 ? tr("Nova oportunidade no painel de vendas (este lead já tinha {0}).", r.do_lead - 1)
        : tr("Registrado no painel de vendas como oportunidade."), 'ok')
      setFeito(r.do_lead)
    }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(false); ref.current = false }
  }}>{busy ? <Spinner /> : <><Icon name="target" size={14} /> {feito ? tr("Em vendas ({0}) · nova oportunidade", feito) : tr("Passar para vendas")}</>}</button>
}
