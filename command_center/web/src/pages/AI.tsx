import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { useGet } from '../api/hooks'
import type { AiAction, AiCommand } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { Banner, Chip, Empty, ErrorState, Loading, POLICY_LABEL, SYS_NAME, Section, statusTone } from '../components/ui'

const ACAO_LABEL: Record<string, string> = { qbo_criar_e_enviar_invoice: 'Criar e enviar invoice', qbo_criar_invoice: 'Criar invoice', qbo_enviar_invoice: 'Enviar invoice', qbo_criar_item: 'Criar item no catálogo', qbo_criar_cliente: 'Criar cliente no QuickBooks', asana_criar_do_modelo: 'Criar tarefa (modelo oficial)', asana_criar_tarefa: 'Criar tarefa', asana_comentar: 'Comentar na tarefa', asana_mover_para_secao: 'Mover tarefa', asana_mover_para_finished: 'Mover para Finished Services', asana_concluir: 'Concluir tarefa', docusign_enviar_waiver: 'Enviar waiver', gmail_rascunho: 'Rascunho de e-mail', gmail_rotular: 'Marcar e-mail' }
const STATUS_LABEL: Record<string, string> = { PROPOSED: 'esperando você', APPROVED: 'aprovada', RUNNING: 'executando', DONE: 'feita', FAILED: 'falhou', REJECTED: 'rejeitada', BLOCKED: 'bloqueada' }
import { ago, fmtDateTime, money, safeJson } from '../components/fmt'
import { useToast } from '../components/Toast'
import { Md } from '../components/Md'

type Args = Record<string, unknown>
function Previa({ a }: { a: AiAction }) {
  const p = safeJson(a.payload) as { args?: Args; alvo?: string; descricao?: string; problemas?: string[] | null } | null
  const args = (p && typeof p === 'object' && p.args && typeof p.args === 'object') ? p.args as Args : null
  const problemas = (p && Array.isArray(p.problemas)) ? p.problemas : []
  if (!args) return <div className="small" style={{ color: 'var(--warn)', marginTop: 6 }}>Sem os dados exatos: a IA descreveu a ação mas não deu os campos. Aprovar vai falhar com esse motivo. Peça no AI Command: "refaça com os argumentos".</div>
  if (a.action.startsWith('qbo_') && Array.isArray(args.linhas)) {
    const linhas = args.linhas as { item_id?: string; quantidade?: number; unitario?: number; descricao?: string; _valor_do_texto?: boolean }[]
    const total = linhas.reduce((t, l) => t + (Number(l.quantidade ?? 1) * Number(l.unitario ?? 0)), 0)
    return <div className="previa"><div className="cond small muted">Prévia da invoice · {a.action === 'qbo_criar_e_enviar_invoice' ? 'aprovar = criar e ENVIAR' : a.action === 'qbo_enviar_invoice' ? 'aprovar = ENVIAR' : 'aprovar = criar (não envia)'}</div>
      {problemas.length > 0 && <div className="banner crit" style={{ margin: '6px 0' }}><b>Proposta incompleta, não dá para aprovar:</b> {problemas.join('; ')}. Diga no AI Command o que falta (ex.: "o valor é $500") e ela refaz.</div>}
      {linhas.some(l => l._valor_do_texto) && <div className="small muted">Valor unitário tirado do que a IA escreveu no texto.</div>}
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

/** O resultado de uma ação executada, em uma frase (invoice, tarefa, waiver, comentário). */
function resumoResultado(a: AiAction): string {
  const r = safeJson(a.result) as Record<string, unknown> | null
  if (!r || typeof r !== 'object') return a.result ? a.result.slice(0, 200) : 'feito'
  if (a.action.startsWith('qbo_') && (r.numero || r.id)) return `Invoice ${r.numero || r.id}${r.total != null ? ` de ${money(Number(r.total))}` : ''} criada${r.enviado ? ` e enviada para ${r.enviado_para}` : r.aviso ? ` (${r.aviso})` : ''}.`
  if (a.action.startsWith('asana_criar') && r.gid) return `Tarefa "${r.nome || ''}" criada no Asana.`
  if (a.action === 'docusign_enviar_waiver') return `Waiver enviada${r.email ? ` para ${r.email}` : ''}.`
  if (a.action === 'asana_comentar') return 'Comentário publicado no Asana.'
  if (a.action.startsWith('asana_mover')) return 'Tarefa movida no Asana.'
  if (r.aplicado === true) return 'Feito.'
  return JSON.stringify(r).slice(0, 200)
}

function ResultadoBox({ a }: { a: AiAction }) {
  if (!a.result) return null
  const r = safeJson(a.result) as Record<string, unknown> | null
  const ok = a.status === 'DONE'
  return <div className={`banner ${ok ? 'ok' : a.status === 'FAILED' ? 'crit' : 'info'}`} style={{ marginTop: 6 }}>
    <b>{ok ? '✓ ' : a.status === 'FAILED' ? '✗ ' : ''}{ok ? resumoResultado(a) : a.status === 'FAILED' ? `Falhou: ${a.result.slice(0, 300)}` : a.result.slice(0, 300)}</b>
    {ok && r && typeof r === 'object' && typeof r.link === 'string' && <> <a className="syslink" href={r.link} target="_blank" rel="noopener noreferrer">{a.action.startsWith('qbo_') ? 'QuickBooks' : 'Asana'} ↗</a></>}
  </div>
}

export function ActionCard({ a, onChange }: { a: AiAction; onChange?: () => void }) {
  const { can } = useAuth()
  const toast = useToast()
  const [busy, setBusy] = useState<'a' | 'r' | null>(null)
  const payload = safeJson(a.payload)
  const incompleta = !!(payload && typeof payload === 'object' && Array.isArray((payload as { problemas?: unknown }).problemas) && ((payload as { problemas: unknown[] }).problemas).length)
  async function decide(kind: 'approve' | 'reject') {
    const comment = kind === 'reject' ? (window.prompt('Motivo (opcional):') ?? undefined) : undefined
    setBusy(kind === 'approve' ? 'a' : 'r')
    try {
      await api.post<{ note?: string }>(`/ai/actions/${a.id}/${kind}`, { comment })
      if (kind === 'reject') { toast('Rejeitada.'); onChange?.(); return }
      toast('Aprovada. Executando…')
      // acompanha até o fim e devolve o resultado, como o dono pediu (10/09): positivo ou negativo, com o que deu
      for (let i = 0; i < 60; i++) {
        await new Promise(res => setTimeout(res, 2000))
        const st = await api.get<AiAction>(`/ai/actions/${a.id}`)
        if (st.status === 'DONE') { toast(`✓ ${resumoResultado(st)}`, 'ok'); break }
        if (st.status === 'FAILED') { toast(`✗ Falhou: ${(st.result || 'sem detalhe').slice(0, 220)}`, 'crit'); break }
        if (i === 59) toast('Ainda executando. O resultado aparece na ação em instantes.')
      }
      onChange?.()
    }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(null) }
  }
  return <div className="act">
    <div className="grow">
      <div className="row wrap"><span className="what">{ACAO_LABEL[a.action] || a.action}</span>{a.system && <Chip tone="outline">{SYS_NAME[a.system] || a.system}</Chip>}<Chip tone={statusTone(a.policy)}>{POLICY_LABEL[a.policy]}</Chip><Chip tone={statusTone(a.status)}>{STATUS_LABEL[a.status] || a.status}</Chip></div>
      {a.reason && <div className="small ink2" style={{ marginTop: 4 }}>{a.reason}</div>}
      {payload !== null && typeof payload === 'object' && (a.status === 'PROPOSED' || a.status === 'APPROVED') && <Previa a={a} />}
      {payload !== null && typeof payload === 'object' && a.status !== 'PROPOSED' && a.status !== 'APPROVED' && <details className="small muted" style={{ marginTop: 4 }}><summary>dados</summary><pre className="mono" style={{ whiteSpace: 'pre-wrap' }}>{JSON.stringify(payload, null, 1).slice(0, 600)}</pre></details>}
      <ResultadoBox a={a} />
      <div className="small muted" style={{ marginTop: 4 }}>{fmtDateTime(a.created_at)}</div>
    </div>
    {a.status === 'PROPOSED' && a.policy !== 'BLOCKED' && <div className="row">
      {can('MANAGER') && <button className="btn primary sm" disabled={!!busy || incompleta} title={incompleta ? 'Proposta incompleta: peça à IA os dados que faltam' : ''} onClick={() => decide('approve')}>{busy === 'a' ? <span className="spin" /> : (a.action.endsWith('enviar_invoice') || a.action === 'docusign_enviar_waiver') ? 'Aprovar e enviar' : 'Aprovar'}</button>}
      {can('OPERATOR') && incompleta && <button className="btn sm" disabled={!!busy} title="O painel acha ou cria o item, resolve o cliente e completa a proposta" onClick={async () => { setBusy('a'); try { const r = await api.post<{ ok: boolean; problemas: string[]; notas: string[] }>(`/ai/actions/${a.id}/complete`); toast(r.ok ? `Completada.${r.notas.length ? ' ' + r.notas.join(' ') : ''} Agora dá para aprovar.` : `Ainda falta: ${r.problemas.join('; ')}`, r.ok ? 'ok' : 'crit'); onChange?.() } catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(null) } }}>{busy === 'a' ? <span className="spin" /> : '⚙ Completar agora'}</button>}
      {can('OPERATOR') && <button className="btn sm" disabled={!!busy} onClick={() => decide('reject')}>{busy === 'r' ? <span className="spin" /> : 'Rejeitar'}</button>}
    </div>}
    {a.policy === 'BLOCKED' && <Chip tone="crit">bloqueada por política</Chip>}
  </div>
}

/** Uma mensagem da conversa: o que a pessoa escreveu e a resposta da IA com as ações. */
function Bolha({ c, onChange, quem }: { c: AiCommand; onChange?: () => void; quem?: string }) {
  const running = c.status === 'QUEUED' || c.status === 'RUNNING'
  const hora = (iso: string) => new Date(iso).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })
  return <div className="chat">
    <div className="msg me"><div className="bub">{c.text.split('\n\nO QUE O DONO JÁ ENSINOU')[0]}</div><div className="when">{quem ? `${quem} · ` : ''}{hora(c.created_at)}</div></div>
    <div className="msg ai">
      <div className="bub">{running ? <span className="row"><span className="spin" /> {c.status === 'QUEUED' ? 'Na fila…' : 'Lendo os sistemas e pensando…'}</span>
        : c.status === 'FAILED' ? <span style={{ color: 'var(--crit)' }}>Falhou: {c.error}</span> : c.output ? <Md text={c.output} /> : <span className="muted">(sem texto)</span>}</div>
      {!!c.actions?.length && <div className="acts">{c.actions.map(a => <ActionCard key={a.id} a={a} onChange={onChange} />)}</div>}
      <div className="when">{c.finished_at ? hora(c.finished_at) : running ? 'agora' : ''}{c.status === 'FAILED' && ' · falhou'}</div>
    </div>
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
  return <Bolha c={c} onChange={() => api.get<AiCommand>(`/ai/commands/${id}`).then(setC)} />
}

interface Threads { threads: { id: number; name: string; role: string; n: number; last_at: string | null }[]; auto: { n: number; last_at: string | null } | null }
interface Thread { commands: AiCommand[]; has_more: boolean }

export function AICommand() {
  const { id } = useParams()
  const nav = useNavigate()
  const loc = useLocation() as { state?: { ask?: string } }
  const { can, user } = useAuth()
  const toast = useToast()
  const [sp, setSp] = useSearchParams()
  const sel = sp.get('u') || 'me'                                   // me | <user_id> | auto
  const sug = useGet<string[]>('/ai/suggestions')
  const threads = useGet<Threads>('/ai/threads', 60000)
  const query = sel === 'auto' ? '/ai/thread?kind=auto' : sel === 'me' ? '/ai/thread' : `/ai/thread?user_id=${sel}`
  const [thread, setThread] = useState<Thread | null>(null)
  const [err, setErr] = useState<ApiError | null>(null)
  const [maisAntigos, setMaisAntigos] = useState<AiCommand[]>([])
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const ta = useRef<HTMLTextAreaElement>(null)
  const fim = useRef<HTMLDivElement>(null)
  const load = () => api.get<Thread>(query).then(t => { setThread(t); setErr(null) }).catch(setErr)
  useEffect(() => { setThread(null); setMaisAntigos([]); load() }, [query]) // eslint-disable-line react-hooks/exhaustive-deps
  const rodando = !!thread?.commands.some(c => c.status === 'QUEUED' || c.status === 'RUNNING')
  useEffect(() => { const t = setInterval(load, rodando ? 3000 : 30000); return () => clearInterval(t) }, [query, rodando]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (loc.state?.ask) { setText(loc.state.ask); ta.current?.focus(); window.history.replaceState({}, '') } }, [loc.state])
  const n = thread?.commands.length || 0
  useEffect(() => { if (n && maisAntigos.length === 0) fim.current?.scrollIntoView({ block: 'end' }) }, [n]) // eslint-disable-line react-hooks/exhaustive-deps
  const cur = id ? Number(id) : null
  const minha = sel === 'me' || (user && String(user.id) === sel)
  const nomeDe = (uid: number) => threads.data?.threads.find(t => t.id === uid)?.name || `usuário #${uid}`
  const todos = [...maisAntigos, ...(thread?.commands || [])]

  async function send() {
    const t = text.trim(); if (!t || busy) return
    setBusy(true)
    try { await api.post<{ id: number }>('/ai/commands', { text: t }); setText(''); if (cur) nav('/ai'); if (sel !== 'me') { const nsp = new URLSearchParams(sp); nsp.delete('u'); setSp(nsp) } await load(); threads.reload(); setTimeout(() => fim.current?.scrollIntoView({ block: 'end' }), 100) }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(false) }
  }
  async function anteriores() {
    const primeiro = todos[0]?.id; if (!primeiro) return
    const t = await api.get<Thread>(query + (query.includes('?') ? '&' : '?') + `before=${primeiro}`)
    setMaisAntigos(m => [...t.commands, ...m]); if (thread) setThread({ ...thread, has_more: t.has_more })
  }
  const separador = (c: AiCommand, i: number) => { const d = c.created_at.slice(0, 10); const ant = todos[i - 1]?.created_at.slice(0, 10); return d !== ant ? <div key={'d' + c.id} className="chat-day">{new Date(d + 'T12:00:00').toLocaleDateString('pt-BR', { weekday: 'long', day: '2-digit', month: 'long' })}</div> : null }

  return <>
    <div className="page-h"><div><h1 className="h1">AI Command</h1><div className="sub small">Uma conversa só, contínua. A IA lê Asana, DocuSign, Gmail e QuickBooks; busca e cria sozinha, e só o envio de invoice e waiver espera você.</div></div></div>
    <div className="grid" style={{ gridTemplateColumns: can('MANAGER') ? 'minmax(0,1fr) 260px' : 'minmax(0,1fr)' }}>
      <div className="stack">
        {!can('OPERATOR') && <Banner tone="info">Seu papel é de leitura: você vê a conversa, mas não envia comandos.</Banner>}
        {cur ? <><div className="small"><a onClick={() => nav('/ai')} style={{ cursor: 'pointer' }}>← voltar à conversa</a></div><CommandView key={cur} id={cur} onDone={load} /></> : <>
          {sel === 'auto' && <Banner tone="info">Conversa automática: eventos do quadro, e-mails e waivers que acordaram a IA sozinha. Ninguém escreve aqui.</Banner>}
          {!minha && sel !== 'auto' && <Banner tone="info">Você está lendo a conversa de <b>{nomeDe(Number(sel))}</b>. Para falar com a IA, volte para a sua.</Banner>}
          {err ? <ErrorState error={err} retry={load} /> : !thread ? <Loading rows={4} /> : todos.length === 0 ? <div className="card card-b">
            <div className="h2" style={{ marginBottom: 10 }}>{sel === 'auto' ? 'Nada automático ainda.' : 'Comece por aqui'}</div>
            {sel !== 'auto' && (sug.data ? <div className="sug">{sug.data.map(s => <button key={s} onClick={() => { setText(s); ta.current?.focus() }}>{s}</button>)}</div> : <Loading rows={2} />)}
          </div> : <div className="stack">
            {(thread.has_more) && <div className="row" style={{ justifyContent: 'center' }}><button className="btn sm" onClick={anteriores}>↑ mensagens anteriores</button></div>}
            {todos.map((c, i) => <div key={c.id}>{separador(c, i)}<Bolha c={c} onChange={load} quem={sel === 'auto' ? 'AUTO' : undefined} /></div>)}
            <div ref={fim} />
          </div>}
        </>}
        {can('OPERATOR') && (minha || cur) && <div className="composer"><div className="box">
          <textarea ref={ta} value={text} onChange={e => setText(e.target.value)} placeholder="Pergunte ou peça algo. Enter envia, Shift+Enter quebra linha." maxLength={4000}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }} rows={2} aria-label="Comando" />
          <button className="btn primary" disabled={busy || !text.trim()} onClick={send}>{busy ? <span className="spin" /> : 'Enviar'}</button>
        </div><div className="small muted">{text.length}/4000 · a resposta pode levar minutos; você pode navegar e voltar.</div></div>}
      </div>
      {can('MANAGER') && <div className="card" style={{ alignSelf: 'start', position: 'sticky', top: 12 }}>
        <div className="card-h"><h2 className="h2">Conversas</h2></div>
        <div className="hist">
          {(threads.data?.threads || []).map(t => <div key={t.id} className={`it${(sel === 'me' && user && t.id === user.id) || sel === String(t.id) ? ' on' : ''}`} onClick={() => { const nsp = new URLSearchParams(sp); if (user && t.id === user.id) nsp.delete('u'); else nsp.set('u', String(t.id)); setSp(nsp); if (cur) nav('/ai?' + nsp.toString()) }}>
            <div className="t">{user && t.id === user.id ? 'Minha conversa' : t.name}</div><div className="small muted">{t.n} mensagem(ns){t.last_at ? ` · ${ago(t.last_at)}` : ''}</div></div>)}
          {threads.data?.auto && <div className={`it${sel === 'auto' ? ' on' : ''}`} onClick={() => { const nsp = new URLSearchParams(sp); nsp.set('u', 'auto'); setSp(nsp); if (cur) nav('/ai?u=auto') }}>
            <div className="t">Automático</div><div className="small muted">{threads.data.auto.n} evento(s){threads.data.auto.last_at ? ` · ${ago(threads.data.auto.last_at)}` : ''}</div></div>}
        </div>
      </div>}
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
