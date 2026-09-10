/* CRM (Kommo) dentro do Command Center — pedido do dono (09/09, feito em 10/09).

   O principal é o CHAT: as conversas do Instagram, Facebook e WhatsApp que chegam no
   Kommo aparecem aqui como uma caixa de entrada, e a resposta sai daqui pelo circuito
   do Salesbot (provado em 24/08). O funil é a segunda aba. Cada link fica junto do seu
   item — nunca uma fila de links no topo. */
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { useGet } from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import { Banner, Chip, Empty, ErrorState, Loading, Spinner, statusTone, type Tone } from '../components/ui'
import { ago, fmtDateTime, money } from '../components/fmt'
import { usePerguntar } from '../components/Perguntar'
import { useToast } from '../components/Toast'

export interface Lead {
  id: number; external_id: string; client_id: number | null; name: string | null
  pipeline_id: string | null; pipeline_name: string | null
  stage_id: string | null; stage_name: string | null; stage_order: number | null
  price: number | null; source: string | null; tags: string[]; responsible: string | null
  contact_name: string | null; contact_email: string | null; contact_phone: string | null
  link: string | null; created_at_src: string | null; updated_at_src: string | null
  last_message_at: string | null; needs_reply: number; last_hook_at?: string | null
  client_name?: string | null; client_pilot?: string | null
  snippet?: string | null; msgs?: number; falhas?: number
}
interface Etapa { id: string; nome: string; ordem: number; leads: Lead[] }
interface Funil { id: string; nome: string; etapas: Etapa[] }
interface Board { funis: Funil[]; total: number; pendentes: number; integracao: { status?: string; last_success_at?: string | null; last_error?: string | null } }
interface Mensagem { id: number; direction: string; author: string | null; text: string | null; at: string | null; source: string | null; status?: string | null; error?: string | null }
interface LeadDetalhe { lead: Lead; mensagens: Mensagem[]; aviso: string | null; responder_habilitado: boolean; chat_ligado: boolean }
interface EtapaViva { id: string; nome: string; ordem: number }
interface FunilVivo { id: string; nome: string; etapas: EtapaViva[] }
interface Inbox { conversas: Lead[]; pendentes: number }
interface Setup { hook_url: string | null; hook_key: boolean; bot_id: string | null; bot_secret: boolean; token: boolean; ultimo_hook: string | null; hooks_hoje: number; fila: number; falhas: number }

/** Origem do lead com a cara do canal: o dono precisa ver de onde veio sem ler. */
export function origemTone(s?: string | null): Tone {
  const t = (s || '').toLowerCase()
  if (t.includes('insta')) return 'accent'
  if (t.includes('face') || t.includes('messenger')) return 'info'
  if (t.includes('whats')) return 'ok'
  if (t.includes('site') || t.includes('web') || t.includes('form')) return 'warn'
  return 'neutral'
}
const ORIGEM_ICONE: Record<string, string> = { instagram: '◎', facebook: 'f', messenger: 'f', whatsapp: '✆', site: '⌂', web: '⌂' }
function iconeDaOrigem(s?: string | null) {
  const t = (s || '').toLowerCase()
  return Object.entries(ORIGEM_ICONE).find(([k]) => t.includes(k))?.[1] || '•'
}
const nomeDo = (l: Lead) => l.contact_name || l.name || `Lead ${l.external_id}`

// ------------------------------------------------------------------ conversa (o chat)
function Conversa({ id, conectado, onChange }: { id: number; conectado: boolean; onChange: () => void }) {
  const { can } = useAuth()
  const toast = useToast()
  const perguntar = usePerguntar()
  const d = useGet<LeadDetalhe>(`/crm/leads/${id}`, 15000)
  const funis = useGet<FunilVivo[]>(conectado ? '/crm/stages' : null)
  const [texto, setTexto] = useState('')
  const [nota, setNota] = useState('')
  const [busy, setBusy] = useState<string | null>(null)
  const fim = useRef<HTMLDivElement | null>(null)
  const l = d.data?.lead
  const etapas = useMemo(() => funis.data?.find(f => f.id === (l?.pipeline_id || ''))?.etapas || [], [funis.data, l?.pipeline_id])
  const total = d.data?.mensagens.length || 0
  useEffect(() => { fim.current?.scrollIntoView({ block: 'end' }) }, [total])

  async function mover(stage: string) {
    setBusy('m')
    try { await api.post(`/crm/leads/${id}/stage`, { stage_id: stage, pipeline_id: l?.pipeline_id }); toast('Lead movido de etapa no Kommo.', 'ok'); d.reload(); onChange() }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(null) }
  }
  async function marcar() {
    const t = await perguntar({ titulo: 'Marcar tag neste lead', campo: 'Tag (ou várias separadas por vírgula)' })
    if (typeof t !== 'string' || !t.trim()) return
    setBusy('t')
    try { await api.post(`/crm/leads/${id}/tags`, { tags: t.split(',').map(x => x.trim()).filter(Boolean) }); toast('Tag marcada no Kommo.', 'ok'); d.reload(); onChange() }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(null) }
  }
  async function anotar() {
    if (!nota.trim()) return
    setBusy('n')
    try { await api.post(`/crm/leads/${id}/note`, { text: nota }); setNota(''); toast('Anotação guardada no lead (não vai para o cliente).', 'ok'); d.reload() }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(null) }
  }
  async function responder() {
    if (!texto.trim()) return
    setBusy('r')
    try {
      const rr = await api.post<{ como: string; aviso?: string }>(`/crm/leads/${id}/reply`, { text: texto })
      setTexto(''); toast(rr.aviso || 'Enviada.', rr.como === 'entregue' ? 'ok' : undefined); d.reload(); onChange()
      if (rr.como !== 'entregue') setTimeout(() => d.reload(), 6000)
    } catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(null) }
  }

  if (d.loading && !d.data) return <div className="read"><Loading /></div>
  if (d.error) return <div className="read"><ErrorState error={d.error} retry={d.reload} /></div>
  if (!l) return null
  const msgs = d.data?.mensagens || []
  // mensagem antiga do canal nativo vem sem texto (a API do Kommo não entrega): vira uma marca
  // compacta — várias seguidas viram uma linha só, com o link para ler no Kommo
  const blocos: (Mensagem | { marca: true; n: number; de: string | null; ate: string | null; entradas: number })[] = []
  for (const m of msgs) {
    if (m.text === null || m.text === undefined) {
      const ult = blocos[blocos.length - 1]
      if (ult && 'marca' in ult) { ult.n++; ult.ate = m.at; if (m.direction === 'entrada') ult.entradas++ }
      else blocos.push({ marca: true, n: 1, de: m.at, ate: m.at, entradas: m.direction === 'entrada' ? 1 : 0 })
    } else blocos.push(m)
  }
  return <div className="read">
    <div className="toolbar">
      <div className="grow" style={{ minWidth: 0 }}>
        <div className="row wrap" style={{ gap: 8 }}>
          <b style={{ fontSize: 16 }}>{nomeDo(l)}</b>
          {l.source && <Chip tone={origemTone(l.source)}>{iconeDaOrigem(l.source)} {l.source}</Chip>}
          {!!l.needs_reply && <Chip tone="warn">esperando resposta</Chip>}
        </div>
        <div className="row wrap small muted" style={{ gap: 10 }}>
          {l.contact_phone && <a href={`tel:${l.contact_phone.replace(/[^\d+]/g, '')}`}>{l.contact_phone}</a>}
          {l.contact_email && <a href={`mailto:${l.contact_email}`}>{l.contact_email}</a>}
          {!!l.price && <span className="mono">{money(l.price)}</span>}
          {l.client_id ? <Link to={`/clients/${l.client_id}`}>card: {l.client_pilot || l.client_name}</Link> : <span>ainda não é cliente</span>}
          {l.link && <a href={l.link} target="_blank" rel="noopener noreferrer">abrir no Kommo ↗</a>}
        </div>
      </div>
      <div className="row wrap" style={{ gap: 6 }}>
        <select className="input" style={{ width: 200, padding: '4px 8px' }} title="Etapa no funil (mudar aqui move no Kommo)" disabled={!can('OPERATOR') || busy === 'm' || etapas.length === 0} value={l.stage_id || ''} onChange={e => mover(e.target.value)}>
          {etapas.length === 0 && <option value={l.stage_id || ''}>{l.stage_name || 'etapa —'}</option>}
          {etapas.map(e => <option key={e.id} value={e.id}>{e.nome}</option>)}
        </select>
        {l.tags.map(t => <span key={t} className="lchip">{t}</span>)}
        {can('OPERATOR') && <button className="btn ghost sm" disabled={busy === 't'} onClick={marcar}>{busy === 't' ? <Spinner /> : '+ tag'}</button>}
      </div>
    </div>
    {d.data?.aviso && <Banner tone="warn">{d.data.aviso}</Banner>}
    <div className="chat" style={{ flex: 1 }}>
      {msgs.length === 0 && <Empty title="Sem mensagens guardadas">O que o lead escreveu antes do chat ser ligado fica só no Kommo. A partir de agora, cada mensagem entra aqui na hora.</Empty>}
      {blocos.map((m, i) => 'marca' in m ? <div key={`marca${i}`} className="msg nota"><div className="bub">{m.n === 1 ? 'uma mensagem' : `${m.n} mensagens`} {l.source ? `pelo ${l.source}` : 'no chat'}{m.entradas && m.entradas < m.n ? ` (${m.entradas} do cliente)` : m.entradas === m.n ? ' do cliente' : ' da nossa parte'} · {m.de ? fmtDateTime(m.de) : ''}{m.n > 1 && m.ate ? ` → ${fmtDateTime(m.ate)}` : ''} · o texto de antes do painel fica no Kommo{l.link && <> — <a href={l.link} target="_blank" rel="noopener noreferrer">ler lá ↗</a></>}</div></div>
        : <div key={m.id} className={`msg ${m.direction === 'entrada' ? 'ai' : m.direction === 'nota' ? 'nota' : 'me'}`}>
        <div className="meta">{m.direction === 'entrada' ? (m.author || 'cliente') : m.direction === 'nota' ? `nota · ${m.author || 'painel'}` : (m.author || 'nós')}{m.at && ` · ${fmtDateTime(m.at)}`}
          {m.direction === 'saida' && m.status === 'queued' && <Chip tone="warn">na fila</Chip>}
          {m.direction === 'saida' && m.status === 'sent' && <Chip tone="ok">entregue</Chip>}
          {m.direction === 'saida' && m.status === 'failed' && <Chip tone="crit">não entregue</Chip>}
        </div>
        <div className="bub">{m.text}</div>
        {m.status === 'failed' && m.error && <div className="small" style={{ color: 'var(--crit)' }}>{m.error}</div>}
      </div>)}
      <div ref={fim} />
    </div>
    {can('OPERATOR') && <div className="stack" style={{ gap: 8 }}>
      {!d.data?.chat_ligado && <Banner tone="warn">{d.data?.responder_habilitado ? 'O bot ainda está esperando esta conversa: dá para responder agora.' : 'O chat ainda não está ligado no Kommo (Salesbot + KOMMO_BOT_ID). Até lá, responda pelo Kommo; a anotação abaixo funciona.'}</Banner>}
      <div className="field"><label>Responder no chat do lead {l.source ? `(${l.source})` : ''}</label>
        <textarea className="input" rows={3} value={texto} placeholder="Escreva a resposta… (Ctrl+Enter envia)" onChange={e => setTexto(e.target.value)} disabled={!d.data?.responder_habilitado} onKeyDown={e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) responder() }} />
        <div className="row wrap"><button className="btn primary sm" disabled={busy === 'r' || !texto.trim() || !d.data?.responder_habilitado} onClick={responder}>{busy === 'r' ? <Spinner /> : 'Enviar no chat'}</button><span className="small muted">Sai pelo bot da conta no canal do lead, com o seu texto.</span></div></div>
      <details><summary className="small">Anotação interna (não vai para o cliente)</summary>
        <div className="field" style={{ marginTop: 6 }}><textarea className="input" rows={2} value={nota} onChange={e => setNota(e.target.value)} />
          <button className="btn sm" disabled={busy === 'n' || !nota.trim()} onClick={anotar}>{busy === 'n' ? <Spinner /> : 'Anotar no lead'}</button></div></details>
    </div>}
  </div>
}

// ------------------------------------------------------------------ caixa de entrada
function CaixaDeEntrada({ conectado }: { conectado: boolean }) {
  const [sp, setSp] = useSearchParams()
  const inbox = useGet<Inbox>('/crm/inbox', 20000)
  const aberto = Number(sp.get('lead')) || null
  const [filtro, setFiltro] = useState('')
  const lista = (inbox.data?.conversas || []).filter(l => !filtro || `${nomeDo(l)} ${l.contact_phone || ''} ${l.contact_email || ''} ${l.source || ''}`.toLowerCase().includes(filtro.toLowerCase()))
  if (inbox.loading && !inbox.data) return <Loading rows={6} />
  if (inbox.error) return <ErrorState error={inbox.error} retry={inbox.reload} />
  return <div className="mail inbox">
    <div className="list">
      <div style={{ padding: 8, borderBottom: '1px solid var(--rule)' }}><input className="input" placeholder="Buscar conversa…" value={filtro} onChange={e => setFiltro(e.target.value)} /></div>
      {lista.length === 0 && <div style={{ padding: 16 }}><Empty title="Nenhuma conversa ainda">Quando o chat estiver ligado no Kommo, cada mensagem do Instagram, Facebook e WhatsApp aparece aqui na hora.</Empty></div>}
      {lista.map(l => <div key={l.id} className={`item${aberto === l.id ? ' on' : ''}`} onClick={() => setSp({ lead: String(l.id) })}>
        <div className="from">{!!l.needs_reply && <span style={{ color: 'var(--warn)' }}>● </span>}{nomeDo(l)}</div>
        <div className="when">{l.last_message_at ? ago(l.last_message_at) : ''}</div>
        <div className="subj">{l.snippet || <span className="muted">{l.msgs ? `${l.msgs} mensagem(ns) · texto no Kommo` : 'sem mensagem guardada'}</span>}</div>
        <div className="sug">{l.source && <Chip tone={origemTone(l.source)}>{iconeDaOrigem(l.source)} {l.source}</Chip>}{l.stage_name && <span className="small muted">{l.stage_name}</span>}{!!l.falhas && <Chip tone="crit">{l.falhas} não entregue</Chip>}{l.client_id && <span className="small muted">· {l.client_pilot || l.client_name}</span>}</div>
      </div>)}
    </div>
    {aberto ? <Conversa key={aberto} id={aberto} conectado={conectado} onChange={inbox.reload} /> : <div className="read"><Empty title="Escolha uma conversa">A lista ao lado mostra quem falou por último; quem espera resposta fica no topo com ●.</Empty></div>}
  </div>
}

// ------------------------------------------------------------------ funil (kanban)
function LeadCard({ l, onOpen }: { l: Lead; onOpen: () => void }) {
  return <button className={`tcard lead${l.needs_reply ? ' esperando' : ''}`} onClick={onOpen}>
    <div className="row wrap" style={{ gap: 6 }}>
      <b className="truncate">{nomeDo(l)}</b>
      {!!l.needs_reply && <Chip tone="warn">esperando resposta</Chip>}
    </div>
    <div className="row wrap small muted" style={{ gap: 6 }}>
      {l.source && <Chip tone={origemTone(l.source)}>{iconeDaOrigem(l.source)} {l.source}</Chip>}
      {!!l.price && <span className="mono">{money(l.price)}</span>}
      {l.last_message_at && <span>{fmtDateTime(l.last_message_at)}</span>}
    </div>
    {l.tags.length > 0 && <div className="row wrap" style={{ gap: 4 }}>{l.tags.slice(0, 4).map(t => <span key={t} className="lchip">{t}</span>)}</div>}
    {l.client_id && <div className="small muted truncate">card: {l.client_pilot || l.client_name}</div>}
  </button>
}

function Funil({ b, abrir }: { b: Board; abrir: (id: number) => void }) {
  const [funil, setFunil] = useState<string | null>(null)
  const funis = b.funis
  const atual = funis.find(f => f.id === funil) || funis[0]
  if (!atual || atual.etapas.length === 0) return <Empty title="Nenhum lead espelhado">Clique em “Sincronizar” para trazer o funil do Kommo.</Empty>
  return <>
    {funis.length > 1 && <div className="tabs">{funis.map(f => <button key={f.id} className={atual.id === f.id ? 'on' : ''} onClick={() => setFunil(f.id)}>{f.nome} <span className="count">{f.etapas.reduce((n, e) => n + e.leads.length, 0)}</span></button>)}</div>}
    <div className="board">
      {atual.etapas.map(e => <div className="col" key={e.id}>
        <div className="ch"><span className="truncate">{e.nome}</span><span className="count">{e.leads.length}</span></div>
        <div className="cards">
          {e.leads.length === 0 && <div className="small muted" style={{ padding: 8 }}>vazia</div>}
          {e.leads.map(l => <LeadCard key={l.id} l={l} onOpen={() => abrir(l.id)} />)}
        </div>
      </div>)}
    </div>
  </>
}

// ------------------------------------------------------------------ ligar o chat (admin)
function LigarChat() {
  const s = useGet<Setup>('/crm/setup', 30000)
  const toast = useToast()
  if (!s.data) return null
  const d = s.data
  const pronto = d.hook_key && !!d.bot_id && d.token
  return <details className="card" open={!pronto}><summary style={{ padding: '10px 14px', cursor: 'pointer' }}><b>Ligar o chat</b> <span className="small muted">— {pronto ? (d.ultimo_hook ? `ligado · último sinal do bot ${ago(d.ultimo_hook)} · ${d.hooks_hoje} hoje` : 'configurado, esperando o primeiro sinal do bot') : 'falta configurar no Kommo'}</span></summary>
    <div className="card-b stack">
      <div className="row wrap">
        <Chip tone={d.token ? 'ok' : 'crit'}>{d.token ? 'token ✓' : 'sem token'}</Chip>
        <Chip tone={d.hook_key ? 'ok' : 'crit'}>{d.hook_key ? 'chave do hook ✓' : 'sem chave do hook (rode o deploy)'}</Chip>
        <Chip tone={d.bot_id ? 'ok' : 'warn'}>{d.bot_id ? `bot ${d.bot_id} ✓` : 'sem KOMMO_BOT_ID'}</Chip>
        <Chip tone={d.bot_secret ? 'ok' : 'neutral'}>{d.bot_secret ? 'assinatura do bot ✓' : 'sem assinatura (opcional)'}</Chip>
        {!!d.fila && <Chip tone="warn">{d.fila} na fila</Chip>}{!!d.falhas && <Chip tone="crit">{d.falhas} não entregue(s)</Chip>}
      </div>
      {d.hook_url && <div className="field"><label>URL do hook — cole no bloco do widget do Salesbot</label>
        <div className="row wrap"><code className="mono small" style={{ wordBreak: 'break-all' }}>{d.hook_url}</code><button className="btn sm" onClick={() => { navigator.clipboard?.writeText(d.hook_url!).then(() => toast('URL copiada.', 'ok')) }}>copiar</button></div></div>}
      <ol className="small" style={{ margin: 0, paddingLeft: 18, lineHeight: 1.7 }}>
        <li>Kommo → <b>Communication tools → Salesbots</b> → novo bot <b>command-center</b>: um único bloco, o do widget <b>“Chase — responder ao lead”</b> (já instalado), com a URL acima no campo. Nada depois do bloco.</li>
        <li>Kommo → <b>Leads → Sales funnel → Automate</b>: em cada etapa onde o lead conversa, gatilho <b>mensagem recebida</b> → bot <b>command-center</b>.</li>
        <li>Pegue o id do bot na lista (<code>list_item_&lt;id&gt;</code>) e grave <code>KOMMO_BOT_ID=&lt;id&gt;</code> em <code>~/.urace/kommo.env</code>; reinicie o serviço (<code>sudo systemctl restart urace-command-center</code>).</li>
        <li>Mande uma mensagem de teste pelo Instagram: ela aparece em Conversas. Responda daqui: sai no chat como mensagem do bot, com o seu texto.</li>
      </ol>
    </div></details>
}

// ------------------------------------------------------------------ página
export function CRM({ vista }: { vista: 'chat' | 'funil' }) {
  const { can } = useAuth()
  const toast = useToast()
  const nav = useNavigate()
  const b = useGet<Board>('/crm/board', 60000)
  const [busy, setBusy] = useState(false)
  const desconectado = (b.data?.integracao?.status || '') !== 'CONNECTED'

  async function sincronizar() {
    setBusy(true)
    try { const r = await api.post<{ ok: boolean; leads?: number; ligados?: number; motivo?: string }>('/crm/sync', {}); toast(r.ok ? `${r.leads} leads do Kommo, ${r.ligados} ligados a um card.` : `Kommo: ${r.motivo}`, r.ok ? 'ok' : 'crit'); b.reload() }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(false) }
  }

  if (b.loading && !b.data) return <Loading rows={6} />
  if (b.error) return <ErrorState error={b.error} retry={b.reload} />
  return <div className="stack">
    <div className="card-h">
      <div><h1 className="h1">{vista === 'chat' ? 'Chat · Kommo' : 'Funil de vendas · Kommo'}</h1>
        <div className="small ink2">{b.data?.total || 0} leads{b.data?.pendentes ? <> · <b>{b.data.pendentes}</b> esperando resposta</> : null}</div></div>
      <div className="grow" />
      <div className="row wrap">
        <Chip tone={statusTone(b.data?.integracao?.status)} dot>{b.data?.integracao?.status || 'DISCONNECTED'}</Chip>
        {can('MANAGER') && <button className="btn" disabled={busy} onClick={sincronizar}>{busy ? <Spinner /> : '⟳ Sincronizar'}</button>}
      </div>
    </div>
    {desconectado && <Banner tone="warn"><b>Kommo não conectado.</b> {b.data?.integracao?.last_error || 'Falta o token da integração privada em ~/.urace/kommo.env (KOMMO_DOMAIN, KOMMO_TOKEN).'} A tela mostra o que já foi espelhado; nada é inventado.</Banner>}
    {vista === 'chat' && can('ADMIN') && <LigarChat />}
    {vista === 'chat' ? <CaixaDeEntrada conectado={!desconectado} /> : b.data && <Funil b={b.data} abrir={id => nav(`/crm/chat?lead=${id}`)} />}
  </div>
}
