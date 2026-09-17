/* CRM (Kommo) dentro do Command Center — pedido do dono (09/09, feito em 10/09).

   O principal é o CHAT: as conversas do Instagram, Facebook e WhatsApp que chegam no
   Kommo aparecem aqui como uma caixa de entrada, e a resposta sai daqui pelo circuito
   do Salesbot (provado em 24/08). O funil é a segunda aba. Cada link fica junto do seu
   item — nunca uma fila de links no topo. */
import { Fragment, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { useGet } from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import { Banner, Chip, Empty, ErrorState, Loading, Scrim, Spinner, statusTone, type Tone } from '../components/ui'
import { Icon } from '../components/Icon'
import { ago, fmtDate, fmtDateLong, fmtDateTime, fmtTime, money } from '../components/fmt'
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
  snippet?: string | null; msgs?: number; falhas?: number; starred?: number | null; contact_avatar?: string | null; profiles?: string | null
}
interface Etapa { id: string; nome: string; ordem: number; leads: Lead[] }
interface Funil { id: string; nome: string; etapas: Etapa[] }
interface Board { funis: Funil[]; total: number; pendentes: number; integracao: { status?: string; last_success_at?: string | null; last_error?: string | null } }
interface Mensagem { id: number; direction: string; author: string | null; text: string | null; at: string | null; source: string | null; status?: string | null; error?: string | null; starred?: number | null }
interface LeadDetalhe { lead: Lead; mensagens: Mensagem[]; aviso: string | null; responder_habilitado: boolean; chat_ligado: boolean }
interface EtapaViva { id: string; nome: string; ordem: number }
interface FunilVivo { id: string; nome: string; etapas: EtapaViva[] }
interface Inbox { conversas: Lead[]; pendentes: number }
interface Perfil { rede: string; rotulo: string; url: string; inferido?: boolean; informado?: boolean }
interface CampoK { campo: string; codigo?: string | null; tipo?: string | null; valor: unknown; enum?: string | null }
interface ContatoK { id: string | null; nome: string | null; primeiro_nome?: string | null; ultimo_nome?: string | null; email: string | null; telefone: string | null; emails: string[]; telefones: string[]; campos_lista: CampoK[]; tags: string[]; responsavel?: string | null; criado_em?: string | null; atualizado_em?: string | null; link?: string | null }
interface EventoK { id: string; tipo: string; rotulo: string; texto: string; em: string | null; por?: string | null; mensagem: boolean; direcao?: string | null; canal?: string | null }
interface LeadK { id: string; nome: string | null; valor: number | null; funil: string | null; etapa: string | null; tags: string[]; responsavel?: string | null; origem?: string | null; origem_kommo?: string | null; campos_lista: CampoK[]; criado_em?: string | null; atualizado_em?: string | null; fechado_em?: string | null; perdido_motivo?: string | null; criado_por?: string | null; link?: string | null; aviso_eventos?: string | null }
interface ConversaK { canal?: string | null; origem?: string | null; lida?: boolean | null; em_trabalho?: boolean | null; criada_em?: string | null; atualizada_em?: string | null; ultima_do_cliente?: string | null; ultima_nossa?: string | null; mensagens?: number; recebidas?: number; enviadas?: number }
interface Detalhe { lead: LeadK; contatos: ContatoK[]; perfis: Perfil[]; conversa: ConversaK | null; eventos: EventoK[]; lido_em?: string }
interface DetalheResp { detalhe: Detalhe; ao_vivo: boolean; em: string | null; aviso: string | null }
interface Setup { hook_url: string | null; webhook_url?: string | null; ultimo_webhook?: string | null; hook_key: boolean; bot_id: string | null; bot_secret: boolean; token: boolean; ultimo_hook: string | null; hooks_hoje: number; fila: number; falhas: number }

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
const REDE_ICONE: Record<string, string> = { instagram: 'instagram', facebook: 'facebook', messenger: 'facebook', whatsapp: 'whatsapp', telegram: 'telegram', site: 'globe', web: 'globe', linkedin: 'globe', tiktok: 'globe' }
function iconeDaRede(s?: string | null) { const t = (s || '').toLowerCase(); return Object.entries(REDE_ICONE).find(([k]) => t.includes(k))?.[1] || 'out' }
const CAMPO_OCULTO = /email|e-mail|phone|telefone|whats|^im$|instagram|facebook|messenger|telegram/i
function Foto({ l, size = 36 }: { l: Lead; size?: number }) {
  const [erro, setErro] = useState(false)
  const n = nomeDo(l)
  const ini = <span className="foto ini" style={{ width: size, height: size, fontSize: Math.round(size * .36) }}>{n.split(/\s+/).slice(0, 2).map(p => p[0]?.toUpperCase() || '').join('')}</span>
  if (!l.contact_avatar || erro) return ini
  return <img className="foto" src={`/ops/api/crm/leads/${l.id}/avatar?v=${encodeURIComponent(l.contact_avatar.slice(-24))}`} alt="" width={size} height={size} style={{ width: size, height: size }} onError={() => setErro(true)} />
}
const nomeDo = (l: Lead) => l.contact_name || l.name || `Lead ${l.external_id}`

// ------------------------------------------------------------------ conversa (o chat)
/** Chip do canal: abre o perfil quando o painel tem o @ (informado ou deduzido); senão abre a busca da rede pelo nome. */
function ChipCanal({ source, perfis, nome }: { source: string | null; perfis?: Perfil[]; nome: string }) {
  if (!source) return null
  const t = source.toLowerCase()
  const p = (perfis || []).find(x => x.rede.toLowerCase() === t || (t.includes('face') && x.rede === 'Facebook') || (t.includes('insta') && x.rede === 'Instagram'))
  const busca = t.includes('insta') ? `https://www.instagram.com/explore/search/keyword/?q=${encodeURIComponent(nome)}`
    : t.includes('face') || t.includes('messenger') ? `https://www.facebook.com/search/people/?q=${encodeURIComponent(nome)}` : null
  const href = p?.url || busca
  const titulo = p ? `abrir ${p.rotulo}` : busca ? `procurar "${nome}" no ${source} (o Kommo não entrega o @ pela API; informe em Dados do lead)` : source
  const chip = <Chip tone={origemTone(source)} title={titulo}>{iconeDaOrigem(source)} {source}{p ? ' ↗' : busca ? ' ⌕' : ''}</Chip>
  return href ? <a href={href} target="_blank" rel="noopener noreferrer" style={{ textDecoration: 'none' }}>{chip}</a> : chip
}

function Conversa({ id, conectado, onChange, onDados }: { id: number; conectado: boolean; onChange: () => void; onDados?: () => void }) {
  const { can } = useAuth()
  const toast = useToast()
  const perguntar = usePerguntar()
  const d = useGet<LeadDetalhe>(`/crm/leads/${id}`, 15000)
  const det = useGet<DetalheResp>(`/crm/leads/${id}/detail`, 120000)
  const funis = useGet<FunilVivo[]>(conectado ? '/crm/stages' : null)
  const [texto, setTexto] = useState('')
  const [nota, setNota] = useState('')
  const [busy, setBusy] = useState<string | null>(null)
  const [soFav, setSoFav] = useState(false)
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
  async function estrelaMsg(m: Mensagem) {
    try { await api.post(`/crm/messages/${m.id}/star`, { starred: !m.starred }); d.reload() } catch (e) { toast((e as ApiError).message, 'crit') }
  }
  async function estrelaLead() {
    try { await api.post(`/crm/leads/${id}/star`, { starred: !l?.starred }); d.reload(); onChange() } catch (e) { toast((e as ApiError).message, 'crit') }
  }
  async function responder() {
    const t = texto.trim()
    if (!t || busy) return                      // Ctrl+Enter durante o envio não manda duas vezes
    setBusy('r')
    try {
      const rr = await api.post<{ como: string; aviso?: string }>(`/crm/leads/${id}/reply`, { text: t })
      setTexto(v => (v.trim() === t ? '' : v))  // o que foi digitado durante o envio fica
      toast(rr.aviso || 'Enviada.', rr.como === 'entregue' ? 'ok' : undefined); d.reload(); onChange()
      if (rr.como !== 'entregue') setTimeout(() => d.reload(), 6000)
    } catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(null) }
  }

  if (d.loading && !d.data) return <div className="read"><Loading /></div>
  if (d.error) return <div className="read"><ErrorState error={d.error} retry={d.reload} /></div>
  if (!l) return null
  const msgs = d.data?.mensagens || []
  let dia = ''
  return <div className="read">
    <div className="toolbar">
      <div className="grow" style={{ minWidth: 0 }}>
        <div className="row wrap" style={{ gap: 8 }}>
          <button className={`star${l.starred ? ' on' : ''}`} onClick={estrelaLead} aria-label={l.starred ? 'Tirar dos favoritos' : 'Favoritar conversa'} title={l.starred ? 'Favorita' : 'Favoritar'}><Icon name="star" size={18} /></button>
          <Foto l={l} size={40} />
          <b style={{ fontSize: 16 }}>{nomeDo(l)}</b>
          <ChipCanal source={l.source} perfis={det.data?.detalhe?.perfis} nome={nomeDo(l)} />
          {!!l.needs_reply && <Chip tone="warn">esperando resposta</Chip>}
          {onDados && <button className="btn sm ld-btn" onClick={onDados}><Icon name="user" size={15} /> Dados do lead</button>}
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
        <button className={`btn ghost sm${soFav ? ' on' : ''}`} onClick={() => setSoFav(v => !v)} title="Só as mensagens favoritas"><Icon name="star" size={14} /> {soFav ? 'todas' : 'favoritas'}</button>
      </div>
    </div>
    {d.data?.aviso && <Banner tone="warn">{d.data.aviso}</Banner>}
    <div className="chat" style={{ flex: 1 }}>
      {msgs.length === 0 && <Empty title="Sem mensagens guardadas">O que o lead escreveu antes do chat ser ligado fica só no Kommo. A partir de agora, cada mensagem entra aqui na hora.</Empty>}
      {soFav && !msgs.some(m => m.starred) && <Empty title="Nenhuma mensagem favorita">Passe o mouse numa mensagem e clique na estrela.</Empty>}
      {msgs.filter(m => !soFav || m.starred).map(m => {
        const d0 = m.at ? fmtDate(m.at) : ''
        const sep = d0 && d0 !== dia
        if (d0) dia = d0
        const semTexto = m.text === null || m.text === undefined
        return <Fragment key={m.id}>
          {sep && <div className="chat-day">{fmtDateLong(m.at)}</div>}
          {semTexto
            ? <div className={`msg marca ${m.direction === 'entrada' ? 'ai' : 'me'}`} title="A API do Kommo não entrega o texto das mensagens de antes do painel">
                <div className="bub"><Icon name={iconeDaRede(m.source || l.source)} size={14} /> {m.direction === 'entrada' ? 'cliente escreveu' : 'respondemos'} · {fmtTime(m.at)}{m.source && m.source !== 'kommo-evento' ? ` · ${m.source}` : ''}{l.link && <> · <a href={l.link} target="_blank" rel="noopener noreferrer">texto no Kommo ↗</a></>}</div>
              </div>
            : <div className={`msg ${m.direction === 'entrada' ? 'ai' : m.direction === 'nota' ? 'nota' : 'me'}`}>
                <div className="meta">{m.direction === 'entrada' ? (m.author || nomeDo(l)) : m.direction === 'nota' ? `nota · ${m.author || 'painel'}` : (m.author || 'nós')}{m.at && ` · ${fmtTime(m.at)}`}
                  {m.direction === 'saida' && m.status === 'queued' && <Chip tone="warn">na fila</Chip>}
                  {m.direction === 'saida' && m.status === 'sent' && <Chip tone="ok">entregue</Chip>}
                  {m.direction === 'saida' && m.status === 'failed' && <Chip tone="crit">não entregue</Chip>}
                </div>
                <div className="bub-row"><div className="bub">{m.text}</div><button className={`star sm${m.starred ? ' on' : ''}`} onClick={() => estrelaMsg(m)} aria-label={m.starred ? 'Tirar favorita' : 'Favoritar mensagem'} title={m.starred ? 'Favorita' : 'Favoritar'}><Icon name="star" size={14} /></button></div>
                {m.status === 'failed' && m.error && <div className="small" style={{ color: 'var(--crit)' }}>{m.error}</div>}
              </div>}
        </Fragment>
      })}
      <div ref={fim} />
    </div>
    {can('OPERATOR') && <div className="stack" style={{ gap: 8 }}>
      {!d.data?.chat_ligado && <Banner tone="warn">{d.data?.responder_habilitado ? 'O bot ainda está esperando esta conversa: dá para responder agora.' : 'O chat ainda não está ligado no Kommo (Salesbot + KOMMO_BOT_ID). Até lá, responda pelo Kommo; a anotação abaixo funciona.'}</Banner>}
      <div className="field"><label>Responder no chat do lead {l.source ? `(${l.source})` : ''}</label>
        <textarea className="input" rows={3} value={texto} placeholder="Escreva a resposta… Enter envia, Shift+Enter quebra a linha" onChange={e => setTexto(e.target.value)} disabled={!d.data?.responder_habilitado} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); responder() } }} />
        <div className="row wrap"><button className="btn primary sm" disabled={busy === 'r' || !texto.trim() || !d.data?.responder_habilitado} onClick={responder}>{busy === 'r' ? <Spinner /> : 'Enviar no chat'}</button><span className="small muted">Sai pelo bot da conta no canal do lead, com o seu texto.</span></div></div>
      <details><summary className="small">Anotação interna (não vai para o cliente)</summary>
        <div className="field" style={{ marginTop: 6 }}><textarea className="input" rows={2} value={nota} onChange={e => setNota(e.target.value)} />
          <button className="btn sm" disabled={busy === 'n' || !nota.trim()} onClick={anotar}>{busy === 'n' ? <Spinner /> : 'Anotar no lead'}</button></div></details>
    </div>}
  </div>
}

// ------------------------------------------------------------------ dados do lead (tudo que o Kommo mostra)
function Linha({ k, children }: { k: string; children: React.ReactNode }) {
  return <div className="ld-row"><span className="k">{k}</span><span className="v">{children}</span></div>
}
function ValorCampo({ v }: { v: unknown }) {
  if (v === null || v === undefined || v === '') return <span className="muted">—</span>
  if (typeof v === 'string' && /^https?:\/\//.test(v)) return <a href={v} target="_blank" rel="noopener noreferrer">{v.replace(/^https?:\/\//, '')} ↗</a>
  if (Array.isArray(v)) return <>{v.map(String).join(', ')}</>
  return <>{String(v)}</>
}
function InformarPerfis({ id, l, atual, onDone }: { id: number; l: Lead; atual: Perfil[]; onDone: () => void }) {
  const { can } = useAuth()
  const toast = useToast()
  const [aberto, setAberto] = useState(false)
  const salvo = (() => { try { return JSON.parse(l.profiles || '{}') as Record<string, string> } catch { return {} } })()
  const [ig, setIg] = useState(salvo.instagram || '')
  const [fb, setFb] = useState(salvo.facebook || '')
  const [busy, setBusy] = useState(false)
  if (!can('OPERATOR')) return null
  const temIg = atual.some(p => p.rede === 'Instagram' && p.informado), temFb = atual.some(p => p.rede === 'Facebook' && p.informado)
  async function salvar() {
    setBusy(true)
    try { await api.post(`/crm/leads/${id}/profiles`, { instagram: ig, facebook: fb }); toast('Perfil guardado. O chip do canal já abre direto.', 'ok'); setAberto(false); onDone() }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(false) }
  }
  return <div style={{ padding: '0 14px 6px' }}>
    {!aberto && <button className="btn ghost sm" onClick={() => setAberto(true)}><Icon name="pencil" size={14} /> {temIg || temFb ? 'editar @ / perfil' : 'informar @ do Instagram ou perfil do Facebook'}</button>}
    {aberto && <div className="stack" style={{ gap: 6 }}>
      <div className="field"><label>Instagram (@usuário)</label><input className="input" value={ig} placeholder="@usuario" onChange={e => setIg(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') salvar() }} /></div>
      <div className="field"><label>Facebook (link do perfil)</label><input className="input" value={fb} placeholder="facebook.com/…" onChange={e => setFb(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') salvar() }} /></div>
      <div className="row"><button className="btn primary sm" disabled={busy} onClick={salvar}>{busy ? <Spinner /> : 'Guardar'}</button><button className="btn ghost sm" onClick={() => setAberto(false)}>cancelar</button></div>
    </div>}
  </div>
}

export function DadosDoLead({ id, l, onClose, onChange }: { id: number; l: Lead; onClose?: () => void; onChange?: () => void }) {
  const d = useGet<DetalheResp>(`/crm/leads/${id}/detail`, 60000)
  if (d.loading && !d.data) return <div className="ld"><Loading rows={5} /></div>
  if (d.error) return <div className="ld"><ErrorState error={d.error} retry={d.reload} /></div>
  const det = d.data!.detalhe
  const lead = det.lead, c = det.contatos[0], conv = det.conversa
  const outrosContato = (c?.campos_lista || []).filter(x => !CAMPO_OCULTO.test(`${x.campo} ${x.codigo || ''} ${x.enum || ''}`))
  const outrosLead = (lead.campos_lista || []).filter(x => !CAMPO_OCULTO.test(`${x.campo} ${x.codigo || ''}`))
  const historico = det.eventos.filter(e => !e.mensagem).slice(-40).reverse()
  return <div className="ld">
    <div className="ld-h"><b>Dados do lead</b><span className="small muted">{d.data!.ao_vivo ? `ao vivo · ${fmtTime(det.lido_em)}` : `retrato de ${fmtDateTime(d.data!.em)}`}</span>
      <button className="btn ghost sm" style={{ marginLeft: 'auto' }} title="Reler no Kommo" onClick={d.reload} aria-label="Reler"><Icon name="refresh" size={16} /></button>
      {onClose && <button className="btn ghost sm" onClick={onClose} aria-label="Fechar"><Icon name="x" size={16} /></button>}</div>
    {d.data!.aviso && <div className="small" style={{ color: 'var(--warn)', padding: '0 14px 8px' }}>{d.data!.aviso}</div>}

    <section className="ld-sec">
      <div className="ld-t">Perfis e canais</div>
      <InformarPerfis id={id} l={l} onDone={() => { d.reload(); onChange?.() }} atual={det.perfis} />
      {det.perfis.map(p => <a key={p.url} className="ld-perfil" href={p.url} target="_blank" rel="noopener noreferrer" title={p.inferido ? 'deduzido do nome/telefone' : 'campo do Kommo'}>
        <span className={`icbox ${iconeDaRede(p.rede) === 'instagram' ? 'red' : iconeDaRede(p.rede) === 'whatsapp' ? 'ok' : iconeDaRede(p.rede) === 'facebook' ? 'info' : ''}`}><Icon name={iconeDaRede(p.rede)} /></span>
        <span className="grow" style={{ minWidth: 0 }}><span className="t truncate">{p.rotulo}</span><span className="s">{p.rede}{p.inferido ? ' · deduzido' : ''}</span></span>
        <Icon name="out" size={16} className="muted" /></a>)}
      {det.perfis.length === 0 && <div className="xs muted" style={{ padding: '0 14px 8px' }}>O Kommo não entrega o @ do Instagram nem o perfil do Facebook pela API. Copie de lá uma vez (Open profile) e informe acima: o chip do canal passa a abrir o perfil direto.</div>}
    </section>

    <section className="ld-sec">
      <div className="ld-t">Contato{det.contatos.length > 1 ? ` (${det.contatos.length})` : ''}</div>
      {!c && <div className="small muted" style={{ padding: '0 14px 8px' }}>Lead sem contato ligado no Kommo.</div>}
      {c && <>
        <Linha k="Nome">{c.nome || '—'}{c.link && <> <a href={c.link} target="_blank" rel="noopener noreferrer" className="small">no Kommo ↗</a></>}</Linha>
        {(c.telefones.length ? c.telefones : c.telefone ? [c.telefone] : []).map(t => <Linha key={t} k="Telefone"><a href={`tel:${t.replace(/[^\d+]/g, '')}`}>{t}</a></Linha>)}
        {(c.emails.length ? c.emails : c.email ? [c.email] : []).map(e => <Linha key={e} k="E-mail"><a href={`mailto:${e}`}>{e}</a></Linha>)}
        {outrosContato.map((x, i) => <Linha key={i} k={x.campo}><ValorCampo v={x.valor} />{x.enum ? <span className="muted small"> · {x.enum}</span> : null}</Linha>)}
        {c.tags.length > 0 && <Linha k="Tags">{c.tags.join(', ')}</Linha>}
        {c.responsavel && <Linha k="Responsável">{c.responsavel}</Linha>}
        {c.criado_em && <Linha k="Criado">{fmtDateTime(c.criado_em)}</Linha>}
      </>}
      {det.contatos.slice(1).map(o => <Linha key={o.id || o.nome || ''} k="Também">{o.nome}{o.telefone ? ` · ${o.telefone}` : ''}{o.email ? ` · ${o.email}` : ''}</Linha>)}
    </section>

    <section className="ld-sec">
      <div className="ld-t">Lead</div>
      <Linha k="Funil">{lead.funil || '—'}{lead.etapa ? <> · <b>{lead.etapa}</b></> : null}</Linha>
      <Linha k="Origem">{lead.origem || lead.origem_kommo || conv?.canal || '—'}</Linha>
      <Linha k="Valor">{lead.valor ? money(lead.valor) : '—'}</Linha>
      <Linha k="Responsável">{lead.responsavel || l.responsible || '—'}</Linha>
      {lead.tags.length > 0 && <Linha k="Tags">{lead.tags.join(', ')}</Linha>}
      {outrosLead.map((x, i) => <Linha key={i} k={x.campo}><ValorCampo v={x.valor} /></Linha>)}
      <Linha k="Criado">{lead.criado_em ? fmtDateTime(lead.criado_em) : '—'}{lead.criado_por ? <span className="muted small"> · {lead.criado_por}</span> : null}</Linha>
      <Linha k="Atualizado">{lead.atualizado_em ? fmtDateTime(lead.atualizado_em) : '—'}</Linha>
      {lead.fechado_em && <Linha k="Fechado">{fmtDateTime(lead.fechado_em)}{lead.perdido_motivo ? ` · ${lead.perdido_motivo}` : ''}</Linha>}
      <Linha k="Id">{lead.id}{lead.link && <> · <a href={lead.link} target="_blank" rel="noopener noreferrer">abrir no Kommo ↗</a></>}</Linha>
    </section>

    {conv && <section className="ld-sec">
      <div className="ld-t">Conversa</div>
      {conv.canal && <Linha k="Canal">{conv.canal}{conv.origem ? <span className="muted small"> · {conv.origem}</span> : null}</Linha>}
      {conv.lida !== undefined && conv.lida !== null && <Linha k="Lida">{conv.lida ? 'sim' : <span style={{ color: 'var(--warn)' }}>não</span>}</Linha>}
      {conv.em_trabalho !== undefined && conv.em_trabalho !== null && <Linha k="Em atendimento">{conv.em_trabalho ? 'sim' : 'não'}</Linha>}
      <Linha k="Do cliente">{conv.ultima_do_cliente ? fmtDateTime(conv.ultima_do_cliente) : '—'}</Linha>
      <Linha k="Nossa">{conv.ultima_nossa ? fmtDateTime(conv.ultima_nossa) : '—'}</Linha>
      {typeof conv.mensagens === 'number' && <Linha k="Mensagens">{conv.mensagens} <span className="muted small">· {conv.recebidas} do cliente · {conv.enviadas} nossas</span></Linha>}
      {conv.criada_em && <Linha k="Aberta">{fmtDateTime(conv.criada_em)}</Linha>}
    </section>}

    <section className="ld-sec">
      <div className="ld-t">Histórico no Kommo</div>
      {historico.length === 0 && <div className="small muted" style={{ padding: '0 14px 8px' }}>{lead.aviso_eventos || 'Nenhum evento além das mensagens.'}</div>}
      {historico.map(e => <div key={e.id} className="ld-ev"><span className="mono small muted">{fmtDateTime(e.em)}</span><span><b>{e.rotulo}</b>{e.texto ? ` · ${e.texto}` : ''}{e.por ? <span className="muted small"> · {e.por}</span> : null}</span></div>)}
    </section>
  </div>
}

// ------------------------------------------------------------------ caixa de entrada
function CaixaDeEntrada({ conectado }: { conectado: boolean }) {
  const [sp, setSp] = useSearchParams()
  const inbox = useGet<Inbox>('/crm/inbox', 20000)
  const aberto = Number(sp.get('lead')) || null
  const [filtro, setFiltro] = useState('')
  const [dados, setDados] = useState(false)
  const [vista, setVista] = useState<'todas' | 'esperando' | 'fav'>('todas')
  const leadAberto = (inbox.data?.conversas || []).find(l => l.id === aberto) || null
  const lista = (inbox.data?.conversas || []).filter(l => !filtro || `${nomeDo(l)} ${l.contact_phone || ''} ${l.contact_email || ''} ${l.source || ''}`.toLowerCase().includes(filtro.toLowerCase()))
    .filter(l => vista === 'todas' || (vista === 'esperando' ? !!l.needs_reply : !!l.starred))
  const toast2 = useToast()
  async function estrela(l: Lead, e: React.MouseEvent) {
    e.stopPropagation()
    try { await api.post(`/crm/leads/${l.id}/star`, { starred: !l.starred }); inbox.reload() } catch (err) { toast2((err as ApiError).message, 'crit') }
  }
  if (inbox.loading && !inbox.data) return <Loading rows={6} />
  if (inbox.error) return <ErrorState error={inbox.error} retry={inbox.reload} />
  return <div className={`mail inbox${aberto ? ' com-dados' : ''}`}>
    <div className="list">
      <div style={{ padding: 8, borderBottom: '1px solid var(--rule)' }} className="stack"><input className="input" placeholder="Buscar conversa…" value={filtro} onChange={e => setFiltro(e.target.value)} />
        <div className="tabs" style={{ alignSelf: 'stretch' }}><button className={vista === 'todas' ? 'on' : ''} onClick={() => setVista('todas')}>Todas</button><button className={vista === 'esperando' ? 'on' : ''} onClick={() => setVista('esperando')}>Esperando <span className="count">{inbox.data?.pendentes || 0}</span></button><button className={vista === 'fav' ? 'on' : ''} onClick={() => setVista('fav')}>★ Favoritas</button></div></div>
      {lista.length === 0 && <div style={{ padding: 16 }}><Empty title="Nenhuma conversa ainda">Quando o chat estiver ligado no Kommo, cada mensagem do Instagram, Facebook e WhatsApp aparece aqui na hora.</Empty></div>}
      {lista.map(l => <div key={l.id} className={`item com-foto${aberto === l.id ? ' on' : ''}`} onClick={() => setSp({ lead: String(l.id) })}>
        <Foto l={l} size={36} />
        <div className="from">{!!l.needs_reply && <span style={{ color: 'var(--warn)' }}>● </span>}{nomeDo(l)}</div>
        <div className="when"><button className={`star sm${l.starred ? ' on' : ''}`} onClick={e => estrela(l, e)} aria-label={l.starred ? 'Tirar dos favoritos' : 'Favoritar'}><Icon name="star" size={13} /></button> {l.last_message_at ? ago(l.last_message_at) : ''}</div>
        <div className="subj">{l.snippet || <span className="muted">{l.msgs ? `${l.msgs} mensagem(ns) · texto no Kommo` : 'sem mensagem guardada'}</span>}</div>
        <div className="sug">{l.source && <Chip tone={origemTone(l.source)}>{iconeDaOrigem(l.source)} {l.source}</Chip>}{l.stage_name && <span className="small muted">{l.stage_name}</span>}{!!l.falhas && <Chip tone="crit">{l.falhas} não entregue</Chip>}{l.client_id && <span className="small muted">· {l.client_pilot || l.client_name}</span>}</div>
      </div>)}
    </div>
    {aberto ? <Conversa key={aberto} id={aberto} conectado={conectado} onChange={inbox.reload} onDados={() => setDados(true)} /> : <div className="read"><Empty title="Escolha uma conversa">A lista ao lado mostra quem falou por último; quem espera resposta fica no topo com ●.</Empty></div>}
    {aberto && leadAberto && <aside className="ld-col"><DadosDoLead key={`c${aberto}`} id={aberto} l={leadAberto} onChange={inbox.reload} /></aside>}
    {dados && aberto && leadAberto && <Scrim onMouseDown={() => setDados(false)}><div className="modal" style={{ maxWidth: 560, padding: 0 }} onMouseDown={e => e.stopPropagation()}><DadosDoLead key={`m${aberto}`} id={aberto} l={leadAberto} onClose={() => setDados(false)} onChange={inbox.reload} /></div></Scrim>}
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
  const textoVivo = !!d.ultimo_webhook
  return <details className="card" open={!pronto || !textoVivo}><summary style={{ padding: '10px 14px', cursor: 'pointer' }}><b>Ligar o chat</b> <span className="small muted">— {pronto ? (d.ultimo_hook ? `bot ligado · último sinal ${ago(d.ultimo_hook)} · ${d.hooks_hoje} hoje` : 'bot configurado, esperando o primeiro sinal') : 'falta configurar no Kommo'}{textoVivo ? ` · texto das mensagens chegando (último ${ago(d.ultimo_webhook)})` : ' · texto das mensagens ainda NÃO chega: falta o webhook do Kommo (abaixo)'}</span></summary>
    <div className="card-b stack">
      {d.webhook_url && <div className="card" style={{ padding: '12px 14px', background: textoVivo ? 'var(--ok-wash)' : 'var(--warn-wash)', borderColor: 'transparent' }}>
        <div className="row wrap" style={{ gap: 8 }}><b>1. Texto de toda mensagem recebida (Instagram, Facebook, WhatsApp) — webhook de conta do Kommo</b>{textoVivo ? <Chip tone="ok">ativo</Chip> : <Chip tone="warn">falta ligar</Chip>}</div>
        <div className="row wrap" style={{ marginTop: 6 }}><code className="mono small" style={{ wordBreak: 'break-all' }}>{d.webhook_url}</code><button className="btn sm" onClick={() => { navigator.clipboard?.writeText(d.webhook_url!).then(() => toast('URL do webhook copiada.', 'ok')) }}>copiar</button></div>
        <ol className="small" style={{ margin: '6px 0 0', paddingLeft: 18, lineHeight: 1.7 }}>
          <li>Kommo → <b>Settings → Integrations → Webhooks</b> → <b>Add webhook</b> → cole a URL acima.</li>
          <li>Marque <b>Incoming message received</b> (e, se aparecerem, <b>Talk added</b> e <b>Talk edited</b>) → <b>Save</b>.</li>
          <li>Mande uma mensagem de teste pelo Instagram: em segundos ela aparece aqui com o texto, sem depender de bot nem de etapa.</li>
        </ol>
      </div>}
      <div className="row wrap" style={{ gap: 8 }}><b>2. Responder daqui — bot command-center (Salesbot)</b></div>
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
