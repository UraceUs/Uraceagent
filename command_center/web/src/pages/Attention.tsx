import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { useGet } from '../api/hooks'
import type { Attention as A, Level } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { Chip, Empty, ErrorState, Loading, Section, levelTone } from '../components/ui'
import { fmtDateTime } from '../components/fmt'
import { useToast } from '../components/Toast'

const LEVELS: Level[] = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']
const LABEL: Record<Level, string> = { CRITICAL: 'Crítico', HIGH: 'Alto', MEDIUM: 'Médio', LOW: 'Baixo' }

function Balao({ a, onDone }: { a: A; onDone: () => void }) {
  const toast = useToast()
  const nav = useNavigate()
  const [text, setText] = useState('')
  const [remember, setRemember] = useState(true)
  const [busy, setBusy] = useState(false)
  async function send() {
    if (!text.trim()) return
    setBusy(true)
    try {
      const r = await api.post<{ command_id: number; remembered: boolean }>('/needs-attention/instruct', { key: a.key, text, remember, title: a.title, why: a.why, client_id: a.client_id, entity_type: a.entity.type, entity_id: a.entity.id === null ? null : String(a.entity.id) })
      toast(r.remembered ? 'Instrução enviada à IA e guardada na memória dela.' : 'Instrução enviada à IA.', 'ok'); onDone(); nav(`/ai/${r.command_id}`)
    } catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(false) }
  }
  return <div className="balao" onClick={e => e.stopPropagation()}>
    <textarea className="input" rows={3} autoFocus value={text} onChange={e => setText(e.target.value)} placeholder={`Diga à IA o que fazer com isto. Ex.: "o valor deste serviço é $350, produto Practice 2T; envie a invoice e a waiver parental".`} onKeyDown={e => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) send() }} />
    <div className="row wrap"><label className="check"><input type="checkbox" checked={remember} onChange={e => setRemember(e.target.checked)} /> guardar na memória da IA {a.client_id ? '(deste cliente)' : `(itens do tipo ${a.entity.type})`}</label><span className="grow" /><button className="btn ghost sm" onClick={onDone}>cancelar</button><button className="btn primary sm" disabled={busy || !text.trim()} onClick={send}>{busy ? <span className="spin" /> : '✦ Enviar à IA'}</button></div>
  </div>
}

export function AttentionList({ items, onChange }: { items: A[]; onChange?: () => void }) {
  const { can } = useAuth()
  const toast = useToast()
  const [busy, setBusy] = useState<string | null>(null)
  const [balao, setBalao] = useState<string | null>(null)
  async function hide(a: A) {
    const reason = window.prompt(`Ocultar este aviso?\n\n"${a.title}"\n\nA tarefa, o envelope ou o e-mail de origem NÃO são apagados. Motivo (opcional):`)
    if (reason === null) return
    setBusy(a.key)
    try { await api.post('/needs-attention/dismiss', { key: a.key, title: a.title, level: a.level, reason }); toast('Aviso ocultado. Dá para restaurar em "ocultos".', 'ok'); onChange?.() }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(null) }
  }
  async function restore(a: A) {
    setBusy(a.key)
    try { await api.post('/needs-attention/restore', { key: a.key }); toast('Aviso restaurado.', 'ok'); onChange?.() }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(null) }
  }
  if (items.length === 0) return <Empty title="Tudo em ordem">Nenhum item precisa de humano agora.</Empty>
  const sysOf = (l: string) => /asana\.com/.test(l) ? 'Asana' : /docusign/.test(l) ? 'DocuSign' : /google\.com/.test(l) ? 'Gmail' : /intuit|qbo/.test(l) ? 'QuickBooks' : 'Origem'
  return <div>{items.map(a => <div className={`att${a.dismissed ? ' dim' : ''}`} key={a.key}>
    <div className={`lv ${a.level}`} />
    <div className="grow">
      <div className="row wrap" style={{ gap: 8 }}>
        <span className="ti">{a.title}</span>
        <Chip tone={levelTone(a.level)}>{LABEL[a.level]}</Chip>
        {a.dismissed && <Chip tone="outline">oculto</Chip>}
        <span className="grow" />
        {a.link && <a className="syslink" href={a.link} target="_blank" rel="noopener noreferrer" title="Abrir no sistema de origem">{sysOf(a.link)} ↗</a>}
      </div>
      <div className="why">{a.why}</div>
      {!!a.facts?.length && <div className="facts">{a.facts.filter(([, v]) => v && v !== '—').map(([k, v]) => <span key={k}><span className="k">{k}</span>{v}</span>)}</div>}
      {a.dismissed && <div className="small muted">Ocultado por {a.dismissed.by || '?'} em {fmtDateTime(a.dismissed.at)}{a.dismissed.reason && <> · “{a.dismissed.reason}”</>}</div>}
      <div className="row wrap small att-acts">
        {a.client_id && <Link className="btn sm" to={`/clients/${a.client_id}`}>{a.action && /respond|responder/i.test(a.action) ? 'Abrir cliente e responder' : 'Abrir cliente'}</Link>}
        {a.entity.type === 'approvals' && <Link className="btn sm" to="/approvals">Ver aprovações</Link>}
        {a.entity.type === 'ai' && <Link className="btn sm" to="/ai">Ver conversa da IA</Link>}
        {a.entity.type === 'integration' && <Link className="btn sm" to="/integrations">Ver integrações</Link>}
        {a.entity.type === 'email' && !a.client_id && <Link className="btn sm" to="/gmail">Abrir na inbox</Link>}
        {!a.client_id && !['approvals', 'ai', 'integration', 'email'].includes(a.entity.type) && a.action && <span className="chip outline">{a.action}</span>}
        <span className="grow" />
        {can('OPERATOR') && !a.dismissed && <button className={`btn sm${balao === a.key ? '' : ' primary'}`} onClick={() => setBalao(b => b === a.key ? null : a.key)} title="Diga à IA o que fazer com este item">✦ Instruir a IA</button>}
        {can('OPERATOR') && !a.dismissed && <button className="btn ghost sm" disabled={busy === a.key} onClick={() => hide(a)} title="Esconde o aviso; não apaga a origem">Ocultar</button>}
        {can('OPERATOR') && a.dismissed && <button className="btn sm" disabled={busy === a.key} onClick={() => restore(a)}>Restaurar</button>}
      </div>
      {balao === a.key && <Balao a={a} onDone={() => setBalao(null)} />}
    </div>
  </div>)}</div>
}

export function AttentionPage() {
  const [showHidden, setShowHidden] = useState(false)
  const { data, error, loading, reload } = useGet<A[]>('/needs-attention' + (showHidden ? '?hidden=1' : ''), 60000)
  const [f, setF] = useState<Level | 'ALL'>('ALL')
  if (error && !data) return <ErrorState error={error} retry={reload} />
  const items = (data || []).filter(a => f === 'ALL' || a.level === f)
  const count = (l: Level) => (data || []).filter(a => a.level === l).length
  const hidden = (data || []).filter(a => a.dismissed).length
  return <>
    <div className="page-h"><div><h1 className="h1">Precisa de atenção</h1>
      <div className="sub small">Só o que a IA não resolveu sozinha, do mais grave para o menos. Ocultar esconde o aviso; a origem fica.</div></div>
      <div className="row"><label className="check"><input type="checkbox" checked={showHidden} onChange={e => setShowHidden(e.target.checked)} /> mostrar ocultos{showHidden && hidden > 0 && <> ({hidden})</>}</label><button className="btn" onClick={reload}>↻ Atualizar</button></div></div>
    <div className="tabs">
      <button className={f === 'ALL' ? 'on' : ''} onClick={() => setF('ALL')}>Todos ({data?.length ?? 0})</button>
      {LEVELS.map(l => <button key={l} className={f === l ? 'on' : ''} onClick={() => setF(l)}>{LABEL[l]} ({count(l)})</button>)}
    </div>
    <Section title="Itens" count={items.length} tight>{loading && !data ? <Loading /> : <AttentionList items={items} onChange={reload} />}</Section>
  </>
}
