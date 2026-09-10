/* CRM (Kommo) dentro do Command Center — pedido do dono (09/09, feito em 10/09).

   O funil como ele já conhece: coluna por etapa, lead por card. Abrir o lead traz
   a conversa, o contato, a origem (Instagram/Facebook/WhatsApp), as tags e a etapa,
   e dá para responder, anotar, mover e ligar ao card do cliente sem sair daqui.
   Cada link fica junto do seu item — nunca uma fila de links no topo. */
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { useGet } from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import { Banner, Chip, Empty, ErrorState, Loading, Spinner, statusTone, type Tone } from '../components/ui'
import { fmtDateTime, money } from '../components/fmt'
import { usePerguntar } from '../components/Perguntar'
import { useToast } from '../components/Toast'

export interface Lead {
  id: number; external_id: string; client_id: number | null; name: string | null
  pipeline_id: string | null; pipeline_name: string | null
  stage_id: string | null; stage_name: string | null; stage_order: number | null
  price: number | null; source: string | null; tags: string[]; responsible: string | null
  contact_name: string | null; contact_email: string | null; contact_phone: string | null
  link: string | null; created_at_src: string | null; updated_at_src: string | null
  last_message_at: string | null; needs_reply: number
  client_name?: string | null; client_pilot?: string | null
}
interface Etapa { id: string; nome: string; ordem: number; leads: Lead[] }
interface Funil { id: string; nome: string; etapas: Etapa[] }
interface Board { funis: Funil[]; total: number; pendentes: number; integracao: { status?: string; last_success_at?: string | null; last_error?: string | null } }
interface Mensagem { id: number; direction: string; author: string | null; text: string | null; at: string | null; source: string | null }
interface LeadDetalhe { lead: Lead; mensagens: Mensagem[]; aviso: string | null; responder_habilitado: boolean }
interface EtapaViva { id: string; nome: string; ordem: number }
interface FunilVivo { id: string; nome: string; etapas: EtapaViva[] }

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

function LeadCard({ l, onOpen }: { l: Lead; onOpen: () => void }) {
  return <button className={`tcard lead${l.needs_reply ? ' esperando' : ''}`} onClick={onOpen}>
    <div className="row wrap" style={{ gap: 6 }}>
      <b className="truncate">{l.name || l.contact_name || `Lead ${l.external_id}`}</b>
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

function LeadModal({ id, conectado, onClose, reload }: { id: number; conectado: boolean; onClose: () => void; reload: () => void }) {
  const { can } = useAuth()
  const toast = useToast()
  const perguntar = usePerguntar()
  const d = useGet<LeadDetalhe>(`/crm/leads/${id}`)
  const funis = useGet<FunilVivo[]>(conectado ? '/crm/stages' : null)   // sem Kommo ligado não bate na API à toa
  const [texto, setTexto] = useState('')
  const [nota, setNota] = useState('')
  const [busy, setBusy] = useState<string | null>(null)
  const l = d.data?.lead
  const etapas = useMemo(() => funis.data?.find(f => f.id === (l?.pipeline_id || ''))?.etapas || [], [funis.data, l?.pipeline_id])

  async function mover(stage: string) {
    setBusy('m')
    try { await api.post(`/crm/leads/${id}/stage`, { stage_id: stage, pipeline_id: l?.pipeline_id }); toast('Lead movido de etapa no Kommo.', 'ok'); d.reload(); reload() }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(null) }
  }
  async function marcar() {
    const t = await perguntar({ titulo: 'Marcar tag neste lead', campo: 'Tag (ou várias separadas por vírgula)' })
    if (typeof t !== 'string' || !t.trim()) return
    setBusy('t')
    try { await api.post(`/crm/leads/${id}/tags`, { tags: t.split(',').map(x => x.trim()).filter(Boolean) }); toast('Tag marcada no Kommo.', 'ok'); d.reload(); reload() }
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
    if (!await perguntar({ titulo: 'Enviar esta resposta ao lead?', texto: 'Sai no canal em que ele falou (Instagram, Facebook, WhatsApp) como mensagem do bot da conta. Não dá para desfazer.', ok: 'Enviar' })) return
    setBusy('r')
    try { const rr = await api.post<{ aviso?: string }>(`/crm/leads/${id}/reply`, { text: texto }); setTexto(''); toast(`Resposta enviada.${rr.aviso ? ' ' + rr.aviso : ''}`, 'ok'); d.reload(); reload() }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(null) }
  }

  return <div className="modal-scrim" onMouseDown={onClose}><div className="modal" style={{ maxWidth: 920 }} onMouseDown={e => e.stopPropagation()}>
    <button className="btn ghost sm close" onClick={onClose} aria-label="Fechar">✕</button>
    {d.loading && !d.data && <Loading />}
    {d.error && <ErrorState error={d.error} retry={d.reload} />}
    {l && <>
      <div><div className="small muted cond">{l.pipeline_name} · {l.stage_name}</div>
        <h2 className="h1" style={{ fontSize: 22 }}>{l.name || l.contact_name || `Lead ${l.external_id}`}</h2>
        <div className="row wrap small ink2">
          {l.source && <Chip tone={origemTone(l.source)}>{iconeDaOrigem(l.source)} veio do {l.source}</Chip>}
          {!!l.price && <span className="mono">{money(l.price)}</span>}
          {l.link && <a className="btn ghost sm" href={l.link} target="_blank" rel="noopener noreferrer">Abrir no Kommo ↗</a>}
        </div></div>
      {d.data?.aviso && <Banner tone="warn">{d.data.aviso}</Banner>}
      <div className="grid g2">
        <div className="stack">
          <div className="card"><div className="card-h"><h2 className="h2">Contato</h2></div><div className="card-b">
            <dl className="dl">
              <dt>Nome</dt><dd>{l.contact_name || '—'}</dd>
              <dt>E-mail</dt><dd>{l.contact_email ? <a href={`mailto:${l.contact_email}`}>{l.contact_email}</a> : '—'}</dd>
              <dt>Telefone</dt><dd>{l.contact_phone ? <a href={`tel:${l.contact_phone.replace(/[^\d+]/g, '')}`}>{l.contact_phone}</a> : '—'}</dd>
              <dt>Card do cliente</dt><dd>{l.client_id ? <Link to={`/clients/${l.client_id}`}>{l.client_pilot || l.client_name}</Link> : <span className="muted">ainda não é cliente</span>}</dd>
            </dl>
          </div></div>
          <div className="card"><div className="card-h"><h2 className="h2">Etapa e tags</h2></div><div className="card-b">
            <div className="field"><label>Etapa no funil</label>
              <select className="input" disabled={!can('OPERATOR') || busy === 'm' || etapas.length === 0} value={l.stage_id || ''} onChange={e => mover(e.target.value)}>
                {etapas.length === 0 && <option value={l.stage_id || ''}>{l.stage_name || '—'}</option>}
                {etapas.map(e => <option key={e.id} value={e.id}>{e.nome}</option>)}
              </select>
              <div className="small muted">Mudar aqui move o lead no Kommo na hora.</div></div>
            <div className="row wrap">{l.tags.map(t => <span key={t} className="lchip">{t}</span>)}
              {can('OPERATOR') && <button className="btn ghost sm" disabled={busy === 't'} onClick={marcar}>{busy === 't' ? <Spinner /> : '+ tag'}</button>}</div>
          </div></div>
        </div>
        <div className="card"><div className="card-h"><h2 className="h2">Conversa</h2><div className="grow" /><span className="small muted">{d.data?.mensagens.length || 0}</span></div>
          <div className="card-b">
            <div className="chat" style={{ maxHeight: 320, overflowY: 'auto' }}>
              {(d.data?.mensagens || []).length === 0 && <Empty>Sem conversa guardada. O que veio antes da integração fica no Kommo.</Empty>}
              {(d.data?.mensagens || []).map(m => <div key={m.id} className={`msg ${m.direction === 'entrada' ? 'ai' : m.direction === 'nota' ? 'nota' : 'me'}`}>
                <div className="meta">{m.direction === 'entrada' ? (m.author || 'cliente') : m.direction === 'nota' ? `nota · ${m.author || 'painel'}` : (m.author || 'nós')}{m.at && ` · ${fmtDateTime(m.at)}`}</div>
                <div className="bub">{m.text}</div>
              </div>)}
            </div>
            {can('OPERATOR') && <>
              <div className="field"><label>Responder no canal do lead</label>
                <textarea className="input" rows={3} value={texto} placeholder="Escreva a resposta…" onChange={e => setTexto(e.target.value)} disabled={!d.data?.responder_habilitado} />
                <div className="row wrap">
                  <button className="btn primary sm" disabled={busy === 'r' || !texto.trim() || !d.data?.responder_habilitado} onClick={responder}>{busy === 'r' ? <Spinner /> : 'Enviar resposta'}</button>
                  {!d.data?.responder_habilitado && <span className="small muted">Sem o Salesbot configurado (KOMMO_BOT_ID), a resposta sai só pelo Kommo. A anotação abaixo funciona.</span>}
                </div></div>
              <div className="field"><label>Anotação interna (não vai para o cliente)</label>
                <textarea className="input" rows={2} value={nota} onChange={e => setNota(e.target.value)} />
                <button className="btn sm" disabled={busy === 'n' || !nota.trim()} onClick={anotar}>{busy === 'n' ? <Spinner /> : 'Anotar no lead'}</button></div>
            </>}
          </div></div>
      </div>
    </>}
  </div></div>
}

export function CRM() {
  const { can } = useAuth()
  const toast = useToast()
  const b = useGet<Board>('/crm/board', 60000)
  const [aberto, setAberto] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const [funil, setFunil] = useState<string | null>(null)
  const funis = b.data?.funis || []
  const atual = funis.find(f => f.id === funil) || funis[0]
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
      <div><h1 className="h1">CRM · Kommo</h1>
        <div className="small ink2">{b.data?.total || 0} leads no espelho{b.data?.pendentes ? <> · <b>{b.data.pendentes}</b> esperando resposta</> : null}</div></div>
      <div className="grow" />
      <div className="row wrap">
        <Chip tone={statusTone(b.data?.integracao?.status)} dot>{b.data?.integracao?.status || 'DISCONNECTED'}</Chip>
        {can('MANAGER') && <button className="btn" disabled={busy} onClick={sincronizar}>{busy ? <Spinner /> : '⟳ Sincronizar'}</button>}
      </div>
    </div>
    {desconectado && <Banner tone="warn"><b>Kommo não conectado.</b> {b.data?.integracao?.last_error || 'Falta o token da integração privada em ~/.urace/kommo.env (KOMMO_DOMAIN, KOMMO_TOKEN).'} A tela mostra o que já foi espelhado; nada é inventado.</Banner>}
    {funis.length > 1 && <div className="tabs">{funis.map(f => <button key={f.id} className={atual?.id === f.id ? 'on' : ''} onClick={() => setFunil(f.id)}>{f.nome} <span className="count">{f.etapas.reduce((n, e) => n + e.leads.length, 0)}</span></button>)}</div>}
    {!atual || atual.etapas.length === 0 ? <Empty title="Nenhum lead espelhado">Clique em “Sincronizar” para trazer o funil do Kommo.</Empty> :
      <div className="board">
        {atual.etapas.map(e => <div className="col" key={e.id}>
          <div className="ch"><span className="truncate">{e.nome}</span><span className="count">{e.leads.length}</span></div>
          <div className="cards">
            {e.leads.length === 0 && <div className="small muted" style={{ padding: 8 }}>vazia</div>}
            {e.leads.map(l => <LeadCard key={l.id} l={l} onOpen={() => setAberto(l.id)} />)}
          </div>
        </div>)}
      </div>}
    {aberto !== null && <LeadModal id={aberto} conectado={!desconectado} onClose={() => setAberto(null)} reload={b.reload} />}
  </div>
}
