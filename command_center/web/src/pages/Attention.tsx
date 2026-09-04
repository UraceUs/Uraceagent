import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { useGet } from '../api/hooks'
import type { Attention as A, Level } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { Chip, Empty, ErrorState, Ext, Loading, Section, levelTone } from '../components/ui'
import { fmtDateTime } from '../components/fmt'
import { useToast } from '../components/Toast'

const LEVELS: Level[] = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']
const LABEL: Record<Level, string> = { CRITICAL: 'Crítico', HIGH: 'Alto', MEDIUM: 'Médio', LOW: 'Baixo' }

export function AttentionList({ items, onChange }: { items: A[]; onChange?: () => void }) {
  const { can } = useAuth()
  const toast = useToast()
  const [busy, setBusy] = useState<string | null>(null)
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
  return <div>{items.map(a => <div className={`att${a.dismissed ? ' dim' : ''}`} key={a.key}>
    <div className={`lv ${a.level}`} />
    <div className="grow">
      <div className="row wrap"><span className="ti">{a.title}</span><Chip tone={levelTone(a.level)}>{LABEL[a.level]}</Chip>{a.dismissed && <Chip tone="outline">oculto</Chip>}</div>
      <div className="why">{a.why}</div>
      {a.dismissed && <div className="small muted">Ocultado por {a.dismissed.by || '?'} em {fmtDateTime(a.dismissed.at)}{a.dismissed.reason && <> · “{a.dismissed.reason}”</>}</div>}
      <div className="row wrap small" style={{ marginTop: 6 }}>
        <span className="chip outline">{a.action}</span>
        {a.client_id && <Link to={`/clients/${a.client_id}`}>Abrir cliente</Link>}
        {a.link && <Ext href={a.link}>Abrir na fonte</Ext>}
        {a.entity.type === 'approvals' && <Link to="/approvals">Ir para aprovações</Link>}
        {a.entity.type === 'ai' && <Link to="/ai">Ver comandos</Link>}
        {a.entity.type === 'integration' && <Link to="/integrations">Integrações</Link>}
        <span className="grow" />
        {can('OPERATOR') && !a.dismissed && <button className="btn ghost sm" disabled={busy === a.key} onClick={() => hide(a)} title="Esconde o aviso; não apaga a origem">Ocultar</button>}
        {can('OPERATOR') && a.dismissed && <button className="btn sm" disabled={busy === a.key} onClick={() => restore(a)}>Restaurar</button>}
      </div>
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
      <div className="sub small">Ordenado por impacto, não por idade: dinheiro, prazo do serviço, waiver que bloqueia a pista, VIP, e-mail devolvido. “Ocultar” esconde o aviso e registra quem e por quê; nada é apagado nas fontes.</div></div>
      <div className="row"><label className="check"><input type="checkbox" checked={showHidden} onChange={e => setShowHidden(e.target.checked)} /> mostrar ocultos{showHidden && hidden > 0 && <> ({hidden})</>}</label><button className="btn" onClick={reload}>↻ Atualizar</button></div></div>
    <div className="tabs">
      <button className={f === 'ALL' ? 'on' : ''} onClick={() => setF('ALL')}>Todos ({data?.length ?? 0})</button>
      {LEVELS.map(l => <button key={l} className={f === l ? 'on' : ''} onClick={() => setF(l)}>{LABEL[l]} ({count(l)})</button>)}
    </div>
    <Section title="Itens" count={items.length} tight>{loading && !data ? <Loading /> : <AttentionList items={items} onChange={reload} />}</Section>
  </>
}
