import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { useGet } from '../api/hooks'
import type { AiAction, AiCommand } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { Banner, Chip, Empty, ErrorState, Loading, POLICY_LABEL, Section, statusTone } from '../components/ui'
import { ago, fmtDateTime, money, safeJson } from '../components/fmt'
import { useToast } from '../components/Toast'
import { Md } from '../components/Md'

type Args = Record<string, unknown>
function Previa({ a }: { a: AiAction }) {
  const p = safeJson(a.payload) as { args?: Args; alvo?: string; descricao?: string } | null
  const args = (p && typeof p === 'object' && p.args && typeof p.args === 'object') ? p.args as Args : null
  if (!args) return <div className="small" style={{ color: 'var(--warn)', marginTop: 6 }}>Sem os dados exatos: a IA descreveu a ação mas não deu os campos. Aprovar vai falhar com esse motivo. Peça no AI Command: "refaça com os argumentos".</div>
  if (a.action.startsWith('qbo_') && Array.isArray(args.linhas)) {
    const linhas = args.linhas as { item_id?: string; quantidade?: number; unitario?: number; descricao?: string }[]
    const total = linhas.reduce((t, l) => t + (Number(l.quantidade ?? 1) * Number(l.unitario ?? 0)), 0)
    return <div className="previa"><div className="cond small muted">Prévia da invoice · {a.action === 'qbo_criar_e_enviar_invoice' ? 'aprovar = criar e ENVIAR' : a.action === 'qbo_enviar_invoice' ? 'aprovar = ENVIAR' : 'aprovar = criar (não envia)'}</div>
      <dl className="dl"><dt>Cliente (QBO)</dt><dd>{String(args.cliente_id ?? '')}{args.email ? <span className="muted"> · {String(args.email)}</span> : null}</dd>{args.vence_em ? <><dt>Vence</dt><dd className="mono">{String(args.vence_em)}</dd></> : null}{args.memo ? <><dt>Memo</dt><dd className="small">{String(args.memo)}</dd></> : null}</dl>
      <table className="tbl" style={{ marginTop: 6 }}><thead><tr><th>Item</th><th>Descrição</th><th>Qtd</th><th>Unitário</th><th>Total</th></tr></thead><tbody>
        {linhas.map((l, i) => <tr key={i}><td className="mono">{l.item_id}</td><td className="small">{l.descricao}</td><td className="mono">{l.quantidade ?? 1}</td><td className="mono">{money(Number(l.unitario ?? 0))}</td><td className="mono">{money(Number(l.quantidade ?? 1) * Number(l.unitario ?? 0))}</td></tr>)}
        <tr><td colSpan={4} className="right"><b>Total</b></td><td className="mono"><b>{money(total)}</b></td></tr></tbody></table></div>
  }
  if (a.action === 'docusign_enviar_waiver') return <div className="previa"><div className="cond small muted">Prévia da waiver · aprovar = ENVIAR pelo DocuSign</div>
    <dl className="dl"><dt>Modelo</dt><dd>{String(args.templateId) === '6dbf2094-39da-4c21-95dd-feda7ac28022' ? 'Parental (piloto menor)' : String(args.templateId) === 'c51aede4-bba5-40df-9f14-24c340e2bd3e' ? 'Adult' : String(args.templateId)}</dd><dt>Assina</dt><dd>{String(args.nome ?? '')} <span className="muted">&lt;{String(args.email ?? '')}&gt;</span></dd>{args.servico ? <><dt>Serviço</dt><dd>{String(args.servico)}</dd></> : null}</dl></div>
  if (a.action === 'asana_comentar') return <div className="previa"><div className="cond small muted">Prévia do comentário no Asana</div><div className="msg-b"><pre style={{ whiteSpace: 'pre-wrap', margin: 0, fontFamily: 'inherit' }}>{String(args.texto ?? '')}</pre></div></div>
  if (a.action === 'gmail_rascunho') return <div className="previa"><div className="cond small muted">Prévia do rascunho (não envia; fica em Rascunhos)</div><dl className="dl"><dt>Para</dt><dd>{String(args.para ?? '')}</dd><dt>Assunto</dt><dd>{String(args.assunto ?? '')}</dd></dl><div className="msg-b"><pre style={{ whiteSpace: 'pre-wrap', margin: 0, fontFamily: 'inherit' }}>{String(args.corpo ?? '')}</pre></div></div>
  return <pre className="mono small muted" style={{ margin: '6px 0 0', whiteSpace: 'pre-wrap' }}>{JSON.stringify(args, null, 1).slice(0, 800)}</pre>
}

export function ActionCard({ a, onChange }: { a: AiAction; onChange?: () => void }) {
  const { can } = useAuth()
  const toast = useToast()
  const [busy, setBusy] = useState<'a' | 'r' | null>(null)
  const payload = safeJson(a.payload)
  async function decide(kind: 'approve' | 'reject') {
    const comment = kind === 'reject' ? (window.prompt('Motivo (opcional):') ?? undefined) : undefined
    setBusy(kind === 'approve' ? 'a' : 'r')
    try { const r = await api.post<{ note?: string }>(`/ai/actions/${a.id}/${kind}`, { comment }); toast(kind === 'approve' ? (r.note || 'Aprovada.') : 'Rejeitada.', kind === 'approve' ? 'ok' : undefined); onChange?.() }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(null) }
  }
  return <div className="act">
    <div className="grow">
      <div className="row wrap"><span className="what">{a.action}</span>{a.system && <Chip tone="outline">{a.system}</Chip>}<Chip tone={statusTone(a.policy)}>{POLICY_LABEL[a.policy]}</Chip><Chip tone={statusTone(a.status)}>{a.status}</Chip></div>
      {a.reason && <div className="small ink2" style={{ marginTop: 4 }}>{a.reason}</div>}
      {payload !== null && typeof payload === 'object' && (a.status === 'PROPOSED' || a.status === 'APPROVED') && <Previa a={a} />}
      {payload !== null && typeof payload === 'object' && a.status !== 'PROPOSED' && a.status !== 'APPROVED' && <details className="small muted" style={{ marginTop: 4 }}><summary>dados</summary><pre className="mono" style={{ whiteSpace: 'pre-wrap' }}>{JSON.stringify(payload, null, 1).slice(0, 600)}</pre></details>}
      {a.result && <div className="small" style={{ marginTop: 4 }}><b>Resultado:</b> {a.result.slice(0, 300)}</div>}
      <div className="small muted" style={{ marginTop: 4 }}>{fmtDateTime(a.created_at)}{a.command_id && <> · comando #{a.command_id}</>}</div>
    </div>
    {a.status === 'PROPOSED' && a.policy !== 'BLOCKED' && <div className="row">
      {can('MANAGER') && <button className="btn primary sm" disabled={!!busy} onClick={() => decide('approve')}>{busy === 'a' ? <span className="spin" /> : (a.action.endsWith('enviar_invoice') || a.action === 'docusign_enviar_waiver') ? 'Aprovar e enviar' : 'Aprovar'}</button>}
      {can('OPERATOR') && <button className="btn sm" disabled={!!busy} onClick={() => decide('reject')}>{busy === 'r' ? <span className="spin" /> : 'Rejeitar'}</button>}
    </div>}
    {a.policy === 'BLOCKED' && <Chip tone="crit">bloqueada por política</Chip>}
  </div>
}

function CommandView({ id, onDone }: { id: number; onDone?: () => void }) {
  const [c, setC] = useState<AiCommand | null>(null)
  const [err, setErr] = useState<ApiError | null>(null)
  useEffect(() => {
    let stop = false
    const tick = () => api.get<AiCommand>(`/ai/commands/${id}`).then(x => { if (stop) return; setC(x); if (x.status === 'QUEUED' || x.status === 'RUNNING') setTimeout(tick, 2500); else onDone?.() }).catch(e => { if (!stop) setErr(e) })
    tick(); return () => { stop = true }
  }, [id]) // eslint-disable-line react-hooks/exhaustive-deps
  if (err) return <ErrorState error={err} />
  if (!c) return <Loading rows={2} />
  const running = c.status === 'QUEUED' || c.status === 'RUNNING'
  return <div className="chat">
    <div className="msg me"><div className="av avatar">EU</div><div className="grow"><div className="meta">{fmtDateTime(c.created_at)}</div><div className="bub">{c.text.split('\n\nO QUE O DONO JÁ ENSINOU')[0]}</div></div></div>
    <div className="msg"><div className="av avatar" style={{ background: 'var(--brand)' }}>AI</div><div className="grow">
      <div className="meta">urace-admin <Chip tone={statusTone(c.status)}>{c.status}</Chip>{c.finished_at && <span>{ago(c.finished_at)}</span>}</div>
      <div className="bub">{running ? <span className="row"><span className="spin" /> {c.status === 'QUEUED' ? 'Na fila…' : 'Pensando e consultando os sistemas…'} <span className="muted small">(pode levar alguns minutos)</span></span>
        : c.status === 'FAILED' ? <span style={{ color: 'var(--crit)' }}>Falhou: {c.error}</span> : c.output ? <Md text={c.output} /> : <span className="muted">(sem texto)</span>}</div>
      {!!c.actions?.length && <div className="acts"><div className="small muted cond">Ações propostas ({c.actions.length})</div>{c.actions.map(a => <ActionCard key={a.id} a={a} />)}</div>}
    </div></div>
  </div>
}

export function AICommand() {
  const { id } = useParams()
  const nav = useNavigate()
  const loc = useLocation() as { state?: { ask?: string } }
  const { can } = useAuth()
  const toast = useToast()
  const sug = useGet<string[]>('/ai/suggestions')
  const hist = useGet<AiCommand[]>('/ai/commands?limit=30')
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const ta = useRef<HTMLTextAreaElement>(null)
  useEffect(() => { if (loc.state?.ask) { setText(loc.state.ask); ta.current?.focus(); window.history.replaceState({}, '') } }, [loc.state])
  const cur = id ? Number(id) : null
  const hojeIso = new Date().toISOString().slice(0, 10)
  const hoje = [...(hist.data || [])].filter(c => c.created_at.startsWith(hojeIso) && !c.text.startsWith('EVENTO AUTOMÁTICO') && !c.text.startsWith('INSTRUÇÃO DO DONO') && !c.text.startsWith('TAREFA:')).reverse()

  async function send() {
    const t = text.trim(); if (!t || busy) return
    setBusy(true)
    try { await api.post<{ id: number }>('/ai/commands', { text: t }); setText(''); if (cur) nav('/ai'); hist.reload() }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(false) }
  }

  return <>
    <div className="page-h"><div><h1 className="h1">AI Command</h1><div className="sub small">Conversa com o agente, que lê Asana, DocuSign, Gmail e QuickBooks. Ele lembra a conversa do dia. O que tem efeito vira ação: segura executa, waiver e invoice esperam sua aprovação.</div></div></div>
    <div className="grid" style={{ gridTemplateColumns: 'minmax(0,1fr) 300px' }}>
      <div className="stack">
        {!can('OPERATOR') && <Banner tone="info">Seu papel é de leitura: você vê o histórico, mas não envia comandos.</Banner>}
        {cur ? <CommandView key={cur} id={cur} onDone={hist.reload} /> : <>
          {hoje.length > 0 ? <div className="stack">{hoje.map(c => <CommandView key={c.id} id={c.id} onDone={hist.reload} />)}</div> : <div className="card card-b">
            <div className="h2" style={{ marginBottom: 10 }}>Sugestões</div>
            {sug.data ? <div className="sug">{sug.data.map(s => <button key={s} onClick={() => { setText(s); ta.current?.focus() }}>{s}</button>)}</div> : <Loading rows={2} />}
          </div>}
        </>}
        {can('OPERATOR') && <div className="composer"><div className="box">
          <textarea ref={ta} value={text} onChange={e => setText(e.target.value)} placeholder="Pergunte ou peça algo. Enter envia, Shift+Enter quebra linha." maxLength={4000}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }} rows={2} aria-label="Comando" />
          <button className="btn primary" disabled={busy || !text.trim()} onClick={send}>{busy ? <span className="spin" /> : 'Enviar'}</button>
        </div><div className="small muted" style={{ marginTop: 4 }}>{text.length}/4000 · a resposta pode levar minutos; você pode navegar e voltar.</div></div>}
      </div>
      <Section title="Histórico" count={hist.data?.length} tight right={cur && <a onClick={() => nav('/ai')} style={{ cursor: 'pointer' }} className="small">novo</a>}>
        {hist.error && !hist.data ? <ErrorState error={hist.error} retry={hist.reload} /> : !hist.data ? <Loading /> : hist.data.length === 0 ? <Empty>Nenhum comando ainda.</Empty> :
          <div>{hist.data.map(c => <div key={c.id} className={`att${cur === c.id ? '' : ' click'}`} style={{ cursor: 'pointer', background: cur === c.id ? 'var(--surface-2)' : undefined }} onClick={() => nav(`/ai/${c.id}`)}>
            <div className="grow"><div className="truncate small" style={{ fontWeight: 500 }}>{c.text}</div><div className="row small muted"><Chip tone={statusTone(c.status)}>{c.status}</Chip>{ago(c.created_at)}</div></div>
          </div>)}</div>}
      </Section>
    </div>
  </>
}

export function Approvals() {
  const { data, error, loading, reload } = useGet<AiAction[]>('/ai/actions?status=PROPOSED', 30000)
  const items = (data || []).filter(a => a.policy !== 'BLOCKED')
  const blocked = (data || []).filter(a => a.policy === 'BLOCKED')
  return <>
    <div className="page-h"><div><h1 className="h1">Aprovações</h1><div className="sub small">Ações que a IA propôs e que exigem decisão humana. Aprovar registra a decisão; a execução chega com o motor de ações (fase 6).</div></div><button className="btn" onClick={reload}>↻</button></div>
    {error && !data ? <ErrorState error={error} retry={reload} /> : loading && !data ? <Loading /> : <>
      <Section title="Pendentes" count={items.length}>{items.length === 0 ? <Empty title="Fila vazia">Nada esperando aprovação.</Empty> : <div className="acts">{items.map(a => <ActionCard key={a.id} a={a} onChange={reload} />)}</div>}</Section>
      {blocked.length > 0 && <Section title="Bloqueadas por política" count={blocked.length}><div className="acts">{blocked.map(a => <ActionCard key={a.id} a={a} />)}</div></Section>}
    </>}
  </>
}

export function Activity() {
  const { data, error, loading, reload } = useGet<{ at: string; actor: string; event: string; entity_type: string | null; entity_id: string | null; detail: string | null }[]>('/ai/activity?limit=200', 30000)
  return <>
    <div className="page-h"><div><h1 className="h1">Atividade da IA</h1><div className="sub small">Trilha imutável: comandos, ações propostas e decisões, em ordem.</div></div><button className="btn" onClick={reload}>↻</button></div>
    <Section title="Eventos" count={data?.length} tight>
      {error && !data ? <ErrorState error={error} retry={reload} /> : loading && !data ? <Loading /> : (data || []).length === 0 ? <Empty>Nenhum evento de IA registrado.</Empty> :
        <div className="tbl-wrap"><table className="tbl"><thead><tr><th>Quando</th><th>Evento</th><th>Quem</th><th>Entidade</th><th>Detalhe</th></tr></thead><tbody>
          {data!.map((r, i) => { const d = safeJson(r.detail); return <tr key={i}><td className="mono nowrap">{fmtDateTime(r.at)}</td><td><Chip tone={r.event.includes('reject') || r.event.includes('fail') ? 'crit' : r.event.includes('approve') ? 'ok' : 'neutral'}>{r.event}</Chip></td><td className="mono small">{r.actor}</td><td className="small">{r.entity_type} {r.entity_id}</td><td className="small ink2" style={{ maxWidth: 480 }}>{typeof d === 'string' ? d : d ? JSON.stringify(d).slice(0, 240) : ''}</td></tr> })}
        </tbody></table></div>}
    </Section>
  </>
}
