import { useState, type FormEvent } from 'react'
import { api, ApiError } from '../api/client'
import { useGet } from '../api/hooks'
import type { ActionPolicy, AuditRow, Integration, Policy } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { Banner, Chip, Empty, ErrorState, Loading, POLICY_LABEL, Section, Spinner, statusTone } from '../components/ui'
import { ago, fmtDateTime, safeJson } from '../components/fmt'
import { useToast } from '../components/Toast'

const DESC: Record<string, string> = {
  asana: 'Quadro U-RACE, sessões e clientes. ADM URACE e Matt tasks são só leitura.',
  docusign: 'Waivers (produção, conta na4). Delivered ≠ assinada.',
  gmail: 'Caixas urace@ e support@. Sem envio a partir daqui.',
  quickbooks: 'Em stand-by por decisão do dono. Invoices só depois de aprovação humana.',
}

export function Integrations() {
  const { can } = useAuth()
  const toast = useToast()
  const { data, error, loading, reload } = useGet<Integration[]>('/integrations', 60000)
  const [busy, setBusy] = useState(false)
  async function check() {
    setBusy(true)
    try { await api.post('/integrations/check'); toast('Sondagem concluída.', 'ok'); reload() } catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(false) }
  }
  return <>
    <div className="page-h"><div><h1 className="h1">Integrações</h1><div className="sub small">Estado real de cada sistema. “Verificar” faz UMA chamada real por sistema e grava o resultado.</div></div>
      {can('OPERATOR') && <button className="btn primary" onClick={check} disabled={busy}>{busy ? <Spinner /> : '⚡'} Verificar agora</button>}</div>
    {error && !data ? <ErrorState error={error} retry={reload} /> : loading && !data ? <Loading /> :
      <div className="grid g2">{(data || []).map(i => { const det = safeJson(i.detail); return <div className="card card-b" key={i.system}>
        <div className="row"><h2 className="h1" style={{ fontSize: 22 }}>{i.system}</h2><Chip tone={statusTone(i.status)} dot>{i.status}</Chip></div>
        <div className="small ink2" style={{ margin: '6px 0 10px' }}>{DESC[i.system]}</div>
        <dl className="dl"><dt>Último sucesso</dt><dd className="mono">{i.last_success_at ? `${fmtDateTime(i.last_success_at)} (${ago(i.last_success_at)})` : '—'}</dd>
          <dt>Última tentativa</dt><dd className="mono">{i.last_attempt_at ? fmtDateTime(i.last_attempt_at) : '—'}</dd>
          <dt>Erros</dt><dd className="mono">{i.error_count}</dd>
          {i.last_error && <><dt>Último erro</dt><dd className="small" style={{ color: 'var(--crit)' }}>{i.last_error}</dd></>}
          {det !== null && typeof det === 'object' && <><dt>Detalhe</dt><dd><pre className="mono small muted" style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{JSON.stringify(det, null, 1).slice(0, 500)}</pre></dd></>}</dl>
      </div> })}</div>}
  </>
}

export function Policies() {
  const toast = useToast()
  const { data, error, loading, reload } = useGet<ActionPolicy[]>('/policies')
  const [busy, setBusy] = useState<string | null>(null)
  async function set(action: string, policy: Policy) {
    if (!window.confirm(`Mudar "${action}" para ${POLICY_LABEL[policy]}?`)) return
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
export function Users() {
  const { user } = useAuth()
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
    if (!window.confirm(`${u.active ? 'Desativar' : 'Reativar'} ${u.email}?`)) return
    try { await api.post(`/users/${u.id}/active`, { active: !u.active }); reload() } catch (ex) { toast((ex as ApiError).message, 'crit') }
  }
  return <>
    <div className="page-h"><div><h1 className="h1">Usuários</h1><div className="sub small">Papéis: Administrador tudo; Gerente aprova e vê financeiro; Operador envia comandos; Leitura só vê.</div></div></div>
    <div className="grid" style={{ gridTemplateColumns: 'minmax(0,1fr) 320px' }}>
      <Section title="Cadastrados" count={data?.length} tight>
        {error && !data ? <ErrorState error={error} retry={reload} /> : loading && !data ? <Loading /> :
          <div className="tbl-wrap"><table className="tbl"><thead><tr><th>Nome</th><th>E-mail</th><th>Papel</th><th>Ativo</th><th>Último login</th><th></th></tr></thead><tbody>
            {(data || []).map(u => <tr key={u.id}><td>{u.name}</td><td className="small">{u.email}</td><td><Chip tone="accent">{u.role}</Chip></td><td>{u.active ? <Chip tone="ok">sim</Chip> : <Chip tone="neutral">não</Chip>}</td><td className="mono small">{u.last_login_at ? ago(u.last_login_at) : 'nunca'}</td>
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
