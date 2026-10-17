import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { useGet } from '../api/hooks'
import type { Attention as A, Level } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { Empty, ErrorState, LEVEL_GLYPH, Loading, PageHeader, Section, levelTone } from '../components/ui'
import { fmtDateTime } from '../components/fmt'
import { usePerguntar } from '../components/Perguntar'
import { useToast } from '../components/Toast'
import { TextoComVoz } from '../components/Voz'
import { Cartao, CdItem, CdLista, type TomD } from '../components/Cartao'
import { tr } from '../i18n'

const LEVELS: Level[] = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']
const LABEL: Record<Level, string> = { CRITICAL: tr("Crítico"), HIGH: tr("Alto"), MEDIUM: tr("Médio"), LOW: tr("Baixo") }

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
      toast(r.remembered ? tr("Instrução enviada à IA e guardada na memória dela.") : tr("Instrução enviada à IA."), 'ok'); onDone(); nav(`/ai/${r.command_id}`)
    } catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(false) }
  }
  return <div className="balao" onClick={e => e.stopPropagation()}>
    <TextoComVoz valor={text} onChange={setText} linhas={3} autoFocus placeholder={tr("Diga (ou dite) à IA o que fazer com isto. Ex.: \"o valor deste serviço é $350, produto Practice 2T; envie a invoice e a waiver parental\".")} />
    <div className="row wrap"><label className="check"><input type="checkbox" checked={remember} onChange={e => setRemember(e.target.checked)} /> {tr("guardar na memória da IA")} {a.client_id ? tr("(deste cliente)") : tr("(itens do tipo {0})", a.entity.type)}</label><span className="grow" /><button className="btn ghost sm" onClick={onDone}>{tr("cancelar")}</button><button className="btn primary sm" disabled={busy || !text.trim()} onClick={send}>{busy ? <span className="spin" /> : tr("✦ Enviar à IA")}</button></div>
  </div>
}

/** `mini`: no painel Hoje, o cartão D compacto, dois por linha */
export function AttentionList({ items, onChange, mini }: { items: A[]; onChange?: () => void; mini?: boolean }) {
  const { can } = useAuth()
  const perguntar = usePerguntar()
  const toast = useToast()
  const [busy, setBusy] = useState<string | null>(null)
  const [balao, setBalao] = useState<string | null>(null)
  async function hide(a: A) {
    const reason = await perguntar({ titulo: tr("Ocultar este aviso?"), texto: tr("\"{0}\"\n\nA tarefa, o envelope ou o e-mail de origem NÃO são apagados.", a.title), campo: tr("Motivo (opcional)"), ok: tr("Ocultar") }) as string | null
    if (reason === null) return
    setBusy(a.key)
    try { await api.post('/needs-attention/dismiss', { key: a.key, title: a.title, level: a.level, reason }); toast(tr("Aviso ocultado. Dá para restaurar em \"ocultos\"."), 'ok'); onChange?.() }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(null) }
  }
  async function restore(a: A) {
    setBusy(a.key)
    try { await api.post('/needs-attention/restore', { key: a.key }); toast(tr("Aviso restaurado."), 'ok'); onChange?.() }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(null) }
  }
  if (items.length === 0) return <Empty title={tr("Tudo em ordem")}>{tr("Nenhum item precisa de humano agora.")}</Empty>
  const sysOf = (l: string) => /asana\.com/.test(l) ? 'Asana' : /docusign/.test(l) ? 'DocuSign' : /google\.com/.test(l) ? 'Gmail' : /intuit|qbo/.test(l) ? 'QuickBooks' : 'Origem'
  // #313: cada aviso no cartão D — o nível em cima, o que é, por quê, os fatos na lista e o que fazer embaixo
  return <div className={`cd-grade cd-dentro${mini ? ' mini' : ''}`}>{items.map((a, n) => <Cartao key={a.key} id={`att-${n}`} mini={mini} className={a.dismissed ? 'cd-apagado' : undefined}
    estado={<><span aria-hidden="true">{LEVEL_GLYPH[a.level]}</span> {LABEL[a.level]}</>} tom={levelTone(a.level) as TomD} nome={a.title}
    sub={[a.why, mini ? (a.facts || []).filter(([, v]) => v && v !== '—').map(([k, v]) => `${k}: ${v}`).join(' · ') : null]}
    acoes={<>
      {a.client_id && <Link className="btn" to={`/clients/${a.client_id}`}>{a.action && /respond|responder/i.test(a.action) ? tr("Abrir cliente e responder") : tr("Abrir cliente")}</Link>}
      {a.entity.type === 'approvals' && <Link className="btn" to="/approvals">{tr("Ver aprovações")}</Link>}
      {a.entity.type === 'ai' && <Link className="btn" to="/ai">{tr("Ver conversa da IA")}</Link>}
      {a.entity.type === 'integration' && <Link className="btn" to="/integrations">{tr("Ver integrações")}</Link>}
      {a.entity.type === 'email' && !a.client_id && <Link className="btn" to="/gmail">{tr("Abrir na inbox")}</Link>}
      {a.entity.type === 'stock' && <Link className="btn" to="/estoque">{a.action || tr("Ver estoque")}</Link>}
      {a.entity.type === 'purchase' && <Link className="btn" to={a.entity.id ? `/compras/${a.entity.id}` : '/pedidos'}>{a.action || tr("Ver compras")}</Link>}
      {a.entity.type === 'booking' && <Link className="btn" to="/site/agendamentos">{a.action || tr("Ver agenda")}</Link>}
      {a.entity.type === 'portal_account' && <Link className="btn" to="/site/contas">{a.action || tr("Ver contas")}</Link>}
      {a.entity.type === 'parts_invoice' && <Link className="btn" to="/balcao">{a.action || tr("Abrir o balcão")}</Link>}
      {a.entity.type === 'checklist_run' && <Link className="btn" to="/checklists">{a.action || tr("Ver checklists")}</Link>}
      {a.entity.type === 'ai_pendencia' && <Link className="btn" to="/ai">{a.action || tr("Ver no AI Command")}</Link>}
      {a.link && <a className="btn" href={a.link} target="_blank" rel="noopener noreferrer" title={tr("Abrir no sistema de origem")}>{sysOf(a.link)} ↗</a>}
      {can('OPERATOR') && !a.dismissed && <button className={`btn${balao === a.key ? '' : ' primary'}`} onClick={() => setBalao(b => b === a.key ? null : a.key)} title={tr("Diga à IA o que fazer com este item")}>{tr("✦ Instruir a IA")}</button>}
      {can('OPERATOR') && !a.dismissed && <button className="btn" disabled={busy === a.key} onClick={() => hide(a)} title={tr("Esconde o aviso; não apaga a origem")}>{tr("ocultar")}</button>}
      {can('OPERATOR') && a.dismissed && !a.dismissed.auto && <button className="btn" disabled={busy === a.key} onClick={() => restore(a)}>{tr("Restaurar")}</button>}</>}>
    {((!mini && !!a.facts?.filter(([, v]) => v && v !== '—').length) || a.dismissed || (!a.client_id && !['approvals', 'ai', 'integration', 'email', 'stock'].includes(a.entity.type) && a.action)) && <CdLista>
      {/* no Hoje (compacto), os fatos vão numa linha só, embaixo do porquê */}
      {!mini && a.facts?.filter(([, v]) => v && v !== '—').map(([k, v]) => <CdItem key={k} tom="neutral" valor={v}>{k}</CdItem>)}
      {!a.client_id && !['approvals', 'ai', 'integration', 'email', 'stock'].includes(a.entity.type) && a.action && <CdItem tom="info" glifo="→">{a.action}</CdItem>}
      {a.dismissed && <CdItem tom="neutral" glifo="—">{a.dismissed.auto ? <>{tr("passou")} · {tr("Ocultado automaticamente:")} {a.dismissed.reason}.</>
        : <>{tr("oculto")} · {tr("Ocultado por")} {a.dismissed.by || '?'} {tr("em")} {fmtDateTime(a.dismissed.at)}{a.dismissed.reason && <> · “{a.dismissed.reason}”</>}</>}</CdItem>}
    </CdLista>}
    {balao === a.key && <div className="cd-form"><Balao a={a} onDone={() => setBalao(null)} /></div>}
  </Cartao>)}</div>
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
    <PageHeader title={tr("Precisa de atenção")} help={tr("Só o que a IA não resolveu sozinha, do mais grave para o menos. Ocultar esconde o aviso; a origem (tarefa, envelope, e-mail) fica onde está.")}>
      <label className="check"><input type="checkbox" checked={showHidden} onChange={e => setShowHidden(e.target.checked)} /> {tr("mostrar ocultos")}{showHidden && hidden > 0 && <> ({hidden})</>}</label><button className="btn" onClick={reload}>↻</button>
    </PageHeader>
    <div className="tabs">
      <button className={f === 'ALL' ? 'on' : ''} onClick={() => setF('ALL')}>{tr("Todos")} <span className="count">{data?.length ?? 0}</span></button>
      {LEVELS.map(l => <button key={l} className={f === l ? 'on' : ''} onClick={() => setF(l)}>{LEVEL_GLYPH[l]} {LABEL[l]} <span className="count">{count(l)}</span></button>)}
    </div>
    <Section title={f === 'ALL' ? tr("Do mais grave para o menos") : LABEL[f]} count={items.length} tight>{loading && !data ? <Loading /> : <AttentionList items={items} onChange={reload} />}</Section>
  </>
}
