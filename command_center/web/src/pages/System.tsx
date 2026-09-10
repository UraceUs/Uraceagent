import { useState, type FormEvent } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { useGet } from '../api/hooks'
import type { ActionPolicy, AuditRow, ContextSource, Integration, Policy } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { Banner, Chip, Empty, ErrorState, Loading, POLICY_LABEL, Section, Spinner, statusTone } from '../components/ui'
import { ago, fmtDateTime, safeJson } from '../components/fmt'
import { usePerguntar } from '../components/Perguntar'
import { useToast } from '../components/Toast'

const DESC: Record<string, string> = {
  asana: 'Quadro U-RACE, sessões e clientes. ADM URACE e Matt tasks são só leitura.',
  docusign: 'Waivers (produção, conta na4). Delivered ≠ assinada.',
  gmail: 'Caixas urace@ e support@. Sem envio a partir daqui.',
  quickbooks: 'Em stand-by por decisão do dono. Invoices só depois de aprovação humana.',
}

function Contexto({ kind }: { kind: 'sheet' | 'file' }) {
  const { can } = useAuth()
  const toast = useToast()
  const { data, error, loading, reload } = useGet<ContextSource[]>('/context')
  const [f, setF] = useState({ title: '', url: '', description: '', sheet_range: '' })
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState<number | 'add' | null>(null)
  const rows = (data || []).filter(c => kind === 'sheet' ? c.kind !== 'file' : c.kind === 'file')
  async function addSheet() {
    setBusy('add')
    try { const r = await api.post<{ id: number; ok: boolean; msg: string }>(f.url.includes('/spreadsheets/') ? '/context/sheet' : '/context/link', f); toast(r.ok === false ? `Cadastrada, mas a leitura falhou: ${r.msg}` : 'Cadastrada e lida.', r.ok === false ? undefined : 'ok'); setF({ title: '', url: '', description: '', sheet_range: '' }); reload() }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(null) }
  }
  async function addFile() {
    if (!file) return
    setBusy('add')
    try {
      const fd = new FormData(); fd.append('file', file); fd.append('title', f.title || file.name); fd.append('description', f.description)
      const csrf = document.cookie.match(/(?:^|;\s*)cc_csrf=([^;]+)/)?.[1] || ''
      const res = await fetch('/ops/api/context/file', { method: 'POST', body: fd, credentials: 'same-origin', headers: { 'X-CSRF': decodeURIComponent(csrf) } })
      if (!res.ok) { const j = await res.json().catch(() => ({})); throw new Error(j.detail || `HTTP ${res.status}`) }
      const j = await res.json(); toast(j.text ? 'Arquivo guardado e texto extraído para a IA.' : 'Arquivo guardado. Sem texto extraído: a IA só vê o nome.', 'ok'); setFile(null); setF({ title: '', url: '', description: '', sheet_range: '' }); reload()
    } catch (e) { toast((e as Error).message, 'crit') } finally { setBusy(null) }
  }
  async function check(c: ContextSource) { setBusy(c.id); try { const r = await api.post<{ ok: boolean; msg: string }>(`/context/${c.id}/check`); toast(r.msg, r.ok ? 'ok' : 'crit'); reload() } catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(null) } }
  async function toggle(c: ContextSource) { try { await api.post(`/context/${c.id}/toggle`); reload() } catch (e) { toast((e as ApiError).message, 'crit') } }
  return <div className="stack">
    {can('OPERATOR') && <div className="card card-b">
      <div className="h2" style={{ marginBottom: 10 }}>{kind === 'sheet' ? 'Cadastrar planilha ou link' : 'Subir arquivo'}</div>
      <div className="grid g2">
        <div className="field"><label>Título</label><input className="input" value={f.title} onChange={e => setF({ ...f, title: e.target.value })} placeholder={kind === 'sheet' ? 'ex.: Tabela de corridas 2026' : 'ex.: Regulamento SKUSA 2026'} /></div>
        {kind === 'sheet' ? <div className="field"><label>Link (Google Sheets ou outro)</label><input className="input" value={f.url} onChange={e => setF({ ...f, url: e.target.value })} placeholder="https://docs.google.com/spreadsheets/d/…" /></div>
          : <div className="field"><label>Arquivo (PDF, TXT, MD, CSV, DOCX, XLSX, imagem; até 25 MB)</label><input className="input" type="file" onChange={e => setFile(e.target.files?.[0] || null)} /></div>}
        {kind === 'sheet' && f.url.includes('/spreadsheets/') && <div className="field"><label>Aba/intervalo (opcional)</label><input className="input" value={f.sheet_range} onChange={e => setF({ ...f, sheet_range: e.target.value })} placeholder="ex.: Sheet1!A1:F80" /></div>}
        <div className="field" style={{ gridColumn: '1 / -1' }}><label>Para que serve (a IA lê isto para decidir quando consultar)</label><input className="input" value={f.description} onChange={e => setF({ ...f, description: e.target.value })} placeholder="ex.: preços de corrida por série; consultar ao montar estimate de pré-corrida" /></div>
      </div>
      <div className="row" style={{ justifyContent: 'flex-end', marginTop: 10 }}><button className="btn primary" disabled={busy === 'add' || (kind === 'sheet' ? !f.url || !f.title : !file)} onClick={kind === 'sheet' ? addSheet : addFile}>{busy === 'add' ? <Spinner /> : kind === 'sheet' ? 'Cadastrar e testar leitura' : 'Subir'}</button></div>
    </div>}
    <Section title={kind === 'sheet' ? 'Planilhas e links' : 'Arquivos'} count={rows.length} tight>
      {error && !data ? <ErrorState error={error} retry={reload} /> : loading && !data ? <Loading /> : rows.length === 0 ? <Empty>{kind === 'sheet' ? 'Nenhuma planilha cadastrada.' : 'Nenhum arquivo. Suba PDFs, regulamentos, tabelas: a IA passa a saber que existem e onde ler.'}</Empty> :
        <div className="tbl-wrap"><table className="tbl"><thead><tr><th>Título</th><th>Para que serve</th><th>{kind === 'sheet' ? 'Onde' : 'Arquivo'}</th><th>Leitura</th><th>Ativo</th><th></th></tr></thead><tbody>
          {rows.map(c => <tr key={c.id} className={c.active ? '' : 'dim'} style={{ opacity: c.active ? 1 : 0.55 }}>
            <td><b>{c.title}</b><div className="small muted">{c.kind === 'sheet' ? 'planilha' : c.kind === 'link' ? 'link' : (c.mime || '')} · {c.added_by_name || '—'} · {fmtDateTime(c.added_at)}</div></td>
            <td className="small ink2" style={{ maxWidth: 320 }}>{c.description}</td>
            <td className="small">{c.kind === 'file' ? <><span className="mono">{c.workspace_name}</span>{c.size ? <div className="muted">{Math.round(c.size / 1024)} KB{c.text_path ? ' · texto extraído' : ' · sem texto'}</div> : null}</> : <a href={c.url || '#'} target="_blank" rel="noopener noreferrer">{c.sheet_range || 'abrir'} ↗</a>}</td>
            <td>{c.last_check_ok === null ? <Chip tone="neutral">não testada</Chip> : <Chip tone={c.last_check_ok ? 'ok' : 'crit'} dot>{c.last_check_ok ? 'ok' : 'falhou'}</Chip>}<div className="small muted" style={{ maxWidth: 260 }}>{c.last_check_msg}</div></td>
            <td>{c.active ? 'sim' : 'não'}</td>
            <td className="nowrap">{can('OPERATOR') && <button className="btn sm" disabled={busy === c.id} onClick={() => check(c)}>{busy === c.id ? <Spinner /> : 'Testar'}</button>} {c.kind === 'file' && <a className="btn sm" href={`/ops/api/context/${c.id}/download`}>⬇</a>} {can('OPERATOR') && <button className="btn ghost sm" onClick={() => toggle(c)}>{c.active ? 'desativar' : 'reativar'}</button>}</td>
          </tr>)}
        </tbody></table></div>}
    </Section>
    <div className="small muted">Tudo que está ativo aqui entra no contexto de todo comando da IA, com o título e o "para que serve". Planilhas ela lê ao vivo; arquivos ficam na pasta <span className="mono">contexto/</span> do agente.</div>
  </div>
}

export function Integrations() {
  const { can } = useAuth()
  const toast = useToast()
  const [sp, setSp] = useSearchParams()
  const tab = (sp.get('v') as 'sys' | 'sheets' | 'files') || 'sys'
  const setTab = (t: string) => { const n = new URLSearchParams(sp); n.set('v', t); setSp(n, { replace: true }) }
  const { data, error, loading, reload } = useGet<Integration[]>('/integrations', 60000)
  const ctx = useGet<ContextSource[]>('/context', 120000)
  const rate = ctx.data?.find(c => c.sheet_id === '160efDlmavKKGbtGfJKCTOV_3Q9JEO3Lc6xA1mEMMNyo')
  const [busy, setBusy] = useState(false)
  async function check() {
    setBusy(true)
    try { await api.post('/integrations/check'); if (rate) await api.post(`/context/${rate.id}/check`); toast('Sondagem concluída.', 'ok'); reload(); ctx.reload() } catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(false) }
  }
  return <>
    <div className="page-h"><div><h1 className="h1">Integrações</h1><div className="sub small">Estado real de cada sistema, mais as planilhas e arquivos que a IA pode consultar. “Verificar” faz UMA chamada real por sistema.</div></div>
      {can('OPERATOR') && tab === 'sys' && <button className="btn primary" onClick={check} disabled={busy}>{busy ? <Spinner /> : '⚡'} Verificar agora</button>}</div>
    <div className="tabs">{([['sys', 'Sistemas'], ['sheets', 'Planilhas e links'], ['files', 'Arquivos']] as const).map(([k, l]) => <button key={k} className={tab === k ? 'on' : ''} onClick={() => setTab(k)}>{l}</button>)}</div>
    {tab === 'sys' && (error && !data ? <ErrorState error={error} retry={reload} /> : loading && !data ? <Loading /> :
      <div className="grid g2">{(data || []).map(i => { const det = safeJson(i.detail); return <div className="card card-b" key={i.system}>
        <div className="row"><h2 className="h1" style={{ fontSize: 22 }}>{i.system}</h2><Chip tone={statusTone(i.status)} dot>{i.status}</Chip></div>
        <div className="small ink2" style={{ margin: '6px 0 10px' }}>{DESC[i.system]}</div>
        <dl className="dl"><dt>Último sucesso</dt><dd className="mono">{i.last_success_at ? `${fmtDateTime(i.last_success_at)} (${ago(i.last_success_at)})` : '—'}</dd>
          <dt>Última tentativa</dt><dd className="mono">{i.last_attempt_at ? fmtDateTime(i.last_attempt_at) : '—'}</dd>
          <dt>Erros</dt><dd className="mono">{i.error_count}</dd>
          {i.last_error && <><dt>Último erro</dt><dd className="small" style={{ color: 'var(--crit)' }}>{i.last_error}</dd></>}
          {det !== null && typeof det === 'object' && <><dt>Detalhe</dt><dd><pre className="mono small muted" style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{JSON.stringify(det, null, 1).slice(0, 500)}</pre></dd></>}</dl>
      </div> })}
      {rate && <div className="card card-b">
        <div className="row"><h2 className="h1" style={{ fontSize: 22 }}>rate card</h2><Chip tone={rate.last_check_ok === null ? 'neutral' : rate.last_check_ok ? 'ok' : 'crit'} dot>{rate.last_check_ok === null ? 'NÃO TESTADA' : rate.last_check_ok ? 'CONNECTED' : 'ERROR'}</Chip></div>
        <div className="small ink2" style={{ margin: '6px 0 10px' }}>Planilha de preços, fonte de verdade acima do catálogo do QuickBooks. A IA lê ao vivo pelo Google.</div>
        <dl className="dl"><dt>Última leitura</dt><dd className="mono">{rate.last_check_at ? `${fmtDateTime(rate.last_check_at)} (${ago(rate.last_check_at)})` : '—'}</dd><dt>Resultado</dt><dd className="small">{rate.last_check_msg || '—'}</dd><dt>Planilha</dt><dd><a href={rate.url || '#'} target="_blank" rel="noopener noreferrer">abrir ↗</a></dd></dl>
      </div>}
      </div>)}
    {tab === 'sheets' && <Contexto kind="sheet" />}
    {tab === 'files' && <Contexto kind="file" />}
  </>
}

export function Policies() {
  const perguntar = usePerguntar()
  const toast = useToast()
  const { data, error, loading, reload } = useGet<ActionPolicy[]>('/policies')
  const [busy, setBusy] = useState<string | null>(null)
  async function set(action: string, policy: Policy) {
    if (!await perguntar({ titulo: `Mudar "${action}" para ${POLICY_LABEL[policy]}?`, texto: 'Muda o que a IA pode fazer sozinha. Fica auditado.', ok: 'Mudar' })) return
    setBusy(action)
    try { await api.put(`/policies/${action}`, { policy }); toast('Política atualizada e auditada.', 'ok'); reload() } catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(null) }
  }
  return <>
    <div className="page-h"><div><h1 className="h1">Políticas da IA</h1><div className="sub small">O que a IA pode fazer sozinha, o que pede confirmação, o que exige aprovação e o que está bloqueado. Apagar nunca destrava.</div></div></div>
    <Banner tone="info">Decisões do dono já em código: invoice só depois de aprovada (04/09); IA não envia e-mail; nada é apagado; Matt tasks e ADM URACE são só leitura.</Banner>
    <Section title="Ações" count={data?.length} tight>
      {error && !data ? <ErrorState error={error} retry={reload} /> : loading && !data ? <Loading /> :
        <div className="tbl-wrap"><table className="tbl"><thead><tr><th>Ação</th><th>Sistema</th><th>Política</th><th>Nota</th><th>Mudar para</th></tr></thead><tbody>
          {(data || []).map(p => <tr key={p.action}><td className="mono">{p.action}</td><td>{p.system}</td><td><Chip tone={statusTone(p.policy)}>{POLICY_LABEL[p.policy]}</Chip></td><td className="small ink2">{p.note}</td>
            <td><select className="input" style={{ width: 170 }} value={p.policy} disabled={busy === p.action || p.action.startsWith('apagar')} onChange={e => set(p.action, e.target.value as Policy)}>
              {(['SAFE', 'REQUIRES_CONFIRMATION', 'REQUIRES_APPROVAL', 'BLOCKED'] as Policy[]).map(x => <option key={x} value={x}>{POLICY_LABEL[x]}</option>)}</select></td></tr>)}
        </tbody></table></div>}
    </Section>
  </>
}

interface U { id: number; email: string; name: string; role: string; active: number; created_at: string; last_login_at: string | null }
const ROLE_PT: Record<string, string> = { ADMIN: 'Administrador', MANAGER: 'Gerente', OPERATOR: 'Operador', VIEWER: 'Leitura' }

function PapelEditavel({ u, self, onChanged }: { u: U; self: boolean; onChanged: () => void }) {
  const perguntar = usePerguntar()
  const toast = useToast()
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  async function mudar(role: string) {
    if (role === u.role) { setOpen(false); return }
    if (!await perguntar({ titulo: `Mudar ${u.name} de ${ROLE_PT[u.role]} para ${ROLE_PT[role]}?`, texto: 'A pessoa é desconectada e entra de novo já com o papel novo.', ok: 'Mudar papel' })) return
    setBusy(true)
    try { await api.post(`/users/${u.id}/role`, { role }); toast(`${u.name} agora é ${ROLE_PT[role]}.`, 'ok'); setOpen(false); onChanged() } catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(false) }
  }
  if (self) return <Chip tone="accent">{ROLE_PT[u.role] || u.role}</Chip>
  if (!open) return <button className="chip accent" style={{ cursor: 'pointer', border: '1px dashed var(--accent)' }} title="Clique para mudar o nível de acesso" onClick={() => setOpen(true)}>{ROLE_PT[u.role] || u.role} ▾</button>
  return <span className="row"><select className="input" style={{ width: 160, padding: '4px 8px' }} autoFocus disabled={busy} value={u.role} onChange={e => mudar(e.target.value)} onBlur={() => !busy && setOpen(false)}>
    {['ADMIN', 'MANAGER', 'OPERATOR', 'VIEWER'].map(r => <option key={r} value={r}>{ROLE_PT[r]}</option>)}</select>{busy && <Spinner />}</span>
}

export function Users() {
  const { user } = useAuth()
  const perguntar = usePerguntar()
  const toast = useToast()
  const { data, error, loading, reload } = useGet<U[]>('/users')
  const [f, setF] = useState({ email: '', name: '', role: 'OPERATOR', password: '' })
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  async function create(e: FormEvent) {
    e.preventDefault(); setBusy(true); setErr(null)
    try { await api.post('/users', f); toast('Usuário criado.', 'ok'); setF({ email: '', name: '', role: 'OPERATOR', password: '' }); reload() } catch (ex) { setErr((ex as ApiError).message) } finally { setBusy(false) }
  }
  async function toggle(u: U) {
    if (!await perguntar({ titulo: `${u.active ? 'Desativar' : 'Reativar'} ${u.email}?`, ok: u.active ? 'Desativar' : 'Reativar', perigo: !!u.active })) return
    try { await api.post(`/users/${u.id}/active`, { active: !u.active }); reload() } catch (ex) { toast((ex as ApiError).message, 'crit') }
  }
  return <>
    <div className="page-h"><div><h1 className="h1">Usuários</h1><div className="sub small">Papéis: Administrador tudo; Gerente aprova e vê financeiro; Operador envia comandos; Leitura só vê.</div></div></div>
    <div className="grid" style={{ gridTemplateColumns: 'minmax(0,1fr) 320px' }}>
      <Section title="Cadastrados" count={data?.length} tight>
        {error && !data ? <ErrorState error={error} retry={reload} /> : loading && !data ? <Loading /> :
          <div className="tbl-wrap"><table className="tbl"><thead><tr><th>Nome</th><th>E-mail</th><th>Papel</th><th>Ativo</th><th>Último login</th><th></th></tr></thead><tbody>
            {(data || []).map(u => <tr key={u.id}><td>{u.name}</td><td className="small">{u.email}</td><td><PapelEditavel u={u} self={u.id === user?.id} onChanged={reload} /></td><td>{u.active ? <Chip tone="ok">sim</Chip> : <Chip tone="neutral">não</Chip>}</td><td className="mono small">{u.last_login_at ? ago(u.last_login_at) : 'nunca'}</td>
              <td>{u.id !== user?.id && <button className="btn sm" onClick={() => toggle(u)}>{u.active ? 'Desativar' : 'Reativar'}</button>}</td></tr>)}
          </tbody></table></div>}
      </Section>
      <Section title="Novo usuário"><form className="stack" onSubmit={create}>
        {err && <Banner tone="crit">{err}</Banner>}
        <div className="field"><label>Nome</label><input className="input" required value={f.name} onChange={e => setF({ ...f, name: e.target.value })} /></div>
        <div className="field"><label>E-mail</label><input className="input" type="email" required value={f.email} onChange={e => setF({ ...f, email: e.target.value })} /></div>
        <div className="field"><label>Papel</label><select className="input" value={f.role} onChange={e => setF({ ...f, role: e.target.value })}>{['ADMIN', 'MANAGER', 'OPERATOR', 'VIEWER'].map(r => <option key={r}>{r}</option>)}</select></div>
        <div className="field"><label>Senha inicial</label><input className="input" type="password" required minLength={5} autoComplete="new-password" value={f.password} onChange={e => setF({ ...f, password: e.target.value })} /><span className="small muted">Mínimo 5 caracteres. Peça para trocar no primeiro acesso.</span></div>
        <button className="btn primary" disabled={busy}>{busy ? <Spinner /> : 'Criar'}</button>
      </form></Section>
    </div>
  </>
}

export function Audit() {
  const { data, error, loading, reload } = useGet<AuditRow[]>('/audit?limit=300')
  const [q, setQ] = useState('')
  const rows = (data || []).filter(r => !q || `${r.event} ${r.actor} ${r.entity_type} ${r.entity_id} ${r.detail}`.toLowerCase().includes(q.toLowerCase()))
  return <>
    <div className="page-h"><div><h1 className="h1">Auditoria</h1><div className="sub small">Registro imutável (gatilhos no banco impedem UPDATE/DELETE). Logins, comandos, decisões, mudanças de política.</div></div>
      <div className="row"><input className="input" style={{ width: 260 }} placeholder="Filtrar" value={q} onChange={e => setQ(e.target.value)} /><button className="btn" onClick={reload}>↻</button></div></div>
    <Section title="Eventos" count={rows.length} tight>
      {error && !data ? <ErrorState error={error} retry={reload} /> : loading && !data ? <Loading /> : rows.length === 0 ? <Empty>Nada registrado.</Empty> :
        <div className="tbl-wrap"><table className="tbl"><thead><tr><th>Quando</th><th>Evento</th><th>Quem</th><th>IP</th><th>Entidade</th><th>Detalhe</th></tr></thead><tbody>
          {rows.map((r, i) => { const d = safeJson(r.detail); return <tr key={r.id ?? i}><td className="mono nowrap">{fmtDateTime(r.at)}</td><td><Chip tone={/fail|reject|denied/.test(r.event) ? 'crit' : /login|approve|create/.test(r.event) ? 'ok' : 'neutral'}>{r.event}</Chip></td><td className="mono small">{r.actor}</td><td className="mono small muted">{r.ip}</td><td className="small">{r.entity_type} {r.entity_id}</td><td className="small ink2" style={{ maxWidth: 420 }}>{typeof d === 'string' ? d : d ? JSON.stringify(d).slice(0, 220) : ''}</td></tr> })}
        </tbody></table></div>}
    </Section>
  </>
}

export function Account() {
  const { user, logout } = useAuth()
  const [f, setF] = useState({ current_password: '', new_password: '', again: '' })
  const [msg, setMsg] = useState<{ tone: 'ok' | 'crit'; text: string } | null>(null)
  const [busy, setBusy] = useState(false)
  async function submit(e: FormEvent) {
    e.preventDefault()
    if (f.new_password !== f.again) { setMsg({ tone: 'crit', text: 'As senhas novas não conferem.' }); return }
    setBusy(true); setMsg(null)
    try { const r = await api.post<{ message: string }>('/auth/password', { current_password: f.current_password, new_password: f.new_password }); setMsg({ tone: 'ok', text: r.message }); setTimeout(() => logout(), 1500) }
    catch (ex) { setMsg({ tone: 'crit', text: (ex as ApiError).message }) } finally { setBusy(false) }
  }
  return <>
    <div className="page-h"><div><h1 className="h1">Minha conta</h1><div className="sub small">{user?.name} · {user?.email} · {user?.role}</div></div></div>
    <div style={{ maxWidth: 420 }}><Section title="Trocar senha"><form className="stack" onSubmit={submit}>
      {msg && <Banner tone={msg.tone}>{msg.text}</Banner>}
      <div className="field"><label>Senha atual</label><input className="input" type="password" autoComplete="current-password" required value={f.current_password} onChange={e => setF({ ...f, current_password: e.target.value })} /></div>
      <div className="field"><label>Nova senha</label><input className="input" type="password" autoComplete="new-password" required minLength={5} value={f.new_password} onChange={e => setF({ ...f, new_password: e.target.value })} /></div>
      <div className="field"><label>Repita a nova</label><input className="input" type="password" autoComplete="new-password" required value={f.again} onChange={e => setF({ ...f, again: e.target.value })} /></div>
      <div className="small muted">Ao trocar, todas as sessões são encerradas e você entra de novo.</div>
      <button className="btn primary" disabled={busy}>{busy ? <Spinner /> : 'Trocar senha'}</button>
    </form></Section></div>
  </>
}
