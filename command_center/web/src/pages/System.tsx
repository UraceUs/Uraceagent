import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { useGet } from '../api/hooks'
import type { ActionPolicy, AuditRow, ContextSource, Integration, Policy } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { Banner, Chip, Empty, ErrorState, Loading, PageHeader, POLICY_LABEL, Section, Spinner, Status, statusTone, SYS_NAME, Thinking } from '../components/ui'
import { Icon } from '../components/Icon'
import { ago, fmtDateTime, safeJson } from '../components/fmt'
import { usePerguntar } from '../components/Perguntar'
import { useToast } from '../components/Toast'

const DESC: Record<string, string> = {
  asana: 'Quadro U-RACE, sessões e clientes. ADM URACE e Matt tasks são só leitura.',
  docusign: 'Waivers (produção, conta na4). Delivered ≠ assinada.',
  gmail: 'Caixas urace@ e support@. Sem envio a partir daqui.',
  quickbooks: 'Em stand-by por decisão do dono. Invoices só depois de aprovação humana.',
  kommo: 'Funil comercial (Instagram, Facebook, WhatsApp). Token da integração privada em ~/.urace/kommo.env. Resposta pelo painel sai como mensagem do bot da conta.',
}

/** O erro da sondagem às vezes vem como JSON ({"motivo": "…"}); a pessoa lê o motivo, não o JSON. */
function motivo(s: string) { const j = safeJson(s) as { motivo?: string } | null; return (j && typeof j === 'object' && typeof j.motivo === 'string') ? j.motivo : s }

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

interface UpdateInfo { versao: { commit: string | null; branch: string | null; quando: string | null; mensagem: string | null }; instalado: boolean; rodando: boolean; ultima: { log: string; resultado: boolean | null; inicio: string | null }; agora: string; novidades?: { atras?: number; commits?: string[]; remoto?: string; erro?: string } }

/** Atualizar o sistema sem terminal (17/09): o pedido vira um arquivo que o servidor vigia; o mesmo
 *  deploy de sempre roda numa unit própria e o log aparece aqui ao vivo. */
function Atualizacao() {
  const toast = useToast()
  const [verificar, setVerificar] = useState(false)
  const [pedido, setPedido] = useState(false)
  const [aberto, setAberto] = useState(false)
  const st = useGet<UpdateInfo>(`/system/update${verificar ? '?verificar=1' : ''}`, 5000)
  const logRef = useRef<HTMLPreElement | null>(null)
  const d = st.data
  const rodando = !!d?.rodando
  useEffect(() => { if (d?.rodando) { setAberto(true); setPedido(false) } }, [d?.rodando])
  useEffect(() => { if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight }, [d?.ultima?.log])
  async function atualizar() {
    setPedido(true)
    try { await api.post('/system/update'); toast('Atualização pedida. O servidor começa em segundos; acompanhe o log.', 'ok'); setAberto(true); st.reload() }
    catch (e) { setPedido(false); toast((e as ApiError).message, 'crit') }
  }
  const reiniciando = !!st.error && (rodando || pedido)
  const nov = d?.novidades
  return <div className="card card-b" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
    <div className="row wrap" style={{ gap: 10 }}>
      <span className="icbox red"><Icon name="refresh" /></span>
      <div className="grow" style={{ minWidth: 0 }}>
        <div style={{ fontWeight: 700 }}>Atualização do sistema</div>
        <div className="small muted">{d?.versao?.commit ? <>versão <span className="mono">{d.versao.commit}</span> · {d.versao.quando ? fmtDateTime(d.versao.quando) : ''} · {d.versao.mensagem}</> : st.error ? 'servidor reiniciando…' : 'lendo a versão…'}</div>
      </div>
      {rodando || reiniciando ? <Thinking label={reiniciando ? 'reiniciando o serviço…' : 'atualizando…'} /> : d?.ultima?.resultado === true && d.ultima.inicio ? <Chip tone="ok" glyph="✓">última: ok · {fmtDateTime(d.ultima.inicio)}</Chip> : d?.ultima?.resultado === false ? <Chip tone="crit" glyph="✕">última falhou</Chip> : null}
      {!verificar ? <button className="btn" onClick={() => setVerificar(true)}>Ver novidades</button>
        : nov?.erro ? <Chip tone="warn">{nov.erro}</Chip> : nov ? <Chip tone={nov.atras ? 'warn' : 'ok'}>{nov.atras ? `${nov.atras} atualização(ões) esperando` : 'já está na versão mais nova'}</Chip> : <Spinner />}
      <button className="btn primary" disabled={rodando || pedido || reiniciando || d?.instalado === false} onClick={atualizar}>{rodando || pedido ? <Spinner /> : <Icon name="refresh" size={16} />} Atualizar agora</button>
    </div>
    {d && !d.instalado && <Banner tone="warn">O botão ainda não está instalado no servidor: rode o deploy uma vez pelo terminal. A partir daí, tudo por aqui.</Banner>}
    {!!nov?.commits?.length && <ul className="small ink2" style={{ margin: 0, paddingLeft: 18 }}>{nov.commits.map((c, i) => <li key={i}>{c}</li>)}</ul>}
    {(d?.ultima?.log || rodando) && <details open={aberto} onToggle={e => setAberto((e.target as HTMLDetailsElement).open)}>
      <summary className="small muted" style={{ cursor: 'pointer' }}>log da última rodada{d?.ultima?.inicio ? ` · ${fmtDateTime(d.ultima.inicio)}` : ''}</summary>
      <pre ref={logRef} className="mono small" style={{ margin: '8px 0 0', maxHeight: 320, overflow: 'auto', whiteSpace: 'pre-wrap', background: 'rgba(0,0,0,.3)', padding: 12, borderRadius: 12 }}>{d?.ultima?.log || 'esperando o servidor começar…'}</pre>
    </details>}
    <div className="xs muted">Roda no servidor o mesmo deploy de sempre (git pull, build, testes, serviço, Caddy). Leva 2–3 min; o painel some por uns segundos quando o serviço reinicia e volta sozinho.</div>
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
    <PageHeader title="Integrações" help={<>Estado real de cada sistema, mais as planilhas e arquivos que a IA pode consultar. “Verificar” faz UMA chamada real por sistema.</>}>
      {can('OPERATOR') && tab === 'sys' && <button className="btn primary" onClick={check} disabled={busy}>{busy ? <Spinner /> : '⚡'} Verificar agora</button>}</PageHeader>
    {can('ADMIN') && tab === 'sys' && <Atualizacao />}
    <div className="tabs">{([['sys', 'Sistemas'], ['sheets', 'Planilhas e links'], ['files', 'Arquivos']] as const).map(([k, l]) => <button key={k} className={tab === k ? 'on' : ''} onClick={() => setTab(k)}>{l}</button>)}</div>
    {tab === 'sys' && (error && !data ? <ErrorState error={error} retry={reload} /> : loading && !data ? <Loading /> :
      <div className="grid g2">{(data || []).map(i => { const det = safeJson(i.detail); const ruim = i.status !== 'CONNECTED' && i.status !== 'SYNCING'; return <div className="card card-b lead" key={i.system} style={{ borderLeftColor: ruim ? 'var(--crit)' : 'var(--ok)' }}>
        <div className="row wrap"><h2 className="h2" style={{ color: 'var(--ink)', fontSize: 16 }}>{SYS_NAME[i.system] || i.system}</h2><Status s={i.status} /><span className="grow" /><span className="small muted mono" title={i.last_success_at ? fmtDateTime(i.last_success_at) : ''}>{i.last_success_at ? `respondeu há ${ago(i.last_success_at)}` : 'nunca respondeu'}</span></div>
        <div className="small ink2" style={{ margin: '6px 0 0' }}>{DESC[i.system]}</div>
        {i.last_error && <div className="banner crit" style={{ marginTop: 8 }}><span className="bi">✕</span><div className="grow small">{motivo(i.last_error)}</div></div>}
        <details className="small muted" style={{ marginTop: 8 }}><summary style={{ cursor: 'pointer' }}>detalhes técnicos</summary>
          <dl className="dl" style={{ marginTop: 6 }}><dt>Última tentativa</dt><dd className="mono">{i.last_attempt_at ? fmtDateTime(i.last_attempt_at) : '—'}</dd><dt>Erros seguidos</dt><dd className="mono">{i.error_count}</dd>
            {det !== null && typeof det === 'object' && <><dt>Detalhe</dt><dd><pre className="mono small muted" style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{JSON.stringify(det, null, 1).slice(0, 500)}</pre></dd></>}</dl></details>
      </div> })}
      {rate && <div className="card card-b">
        <div className="row"><h2 className="h2" style={{ color: 'var(--ink)', fontSize: 16 }}>Rate Card</h2><Status kind={rate.last_check_ok === null ? 'wait' : rate.last_check_ok ? 'ok' : 'crit'} label={rate.last_check_ok === null ? 'não testada' : rate.last_check_ok ? 'lida' : 'falhou'} /></div>
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
    <PageHeader title="Políticas da IA" help={<>O que a IA pode fazer sozinha, o que pede confirmação, o que exige aprovação e o que está bloqueado. Apagar nunca destrava.</>} />
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

interface U { id: number; email: string; name: string; role: string; active: number; created_at: string; last_login_at: string | null; free?: boolean }
const ROLE_PT: Record<string, string> = { ADMIN: 'Administrador', MANAGER: 'Gerente', OPERATOR: 'Operador', VIEWER: 'Leitura' }
const ROLE_O_QUE: Record<string, string> = {
  ADMIN: 'tudo, inclusive usuários, políticas da IA e integrações',
  MANAGER: 'tudo do operador + financeiro (QuickBooks e invoices) e auditoria',
  OPERATOR: 'o dia a dia e as vendas: clientes, serviços, waivers, e-mails, chat, oportunidades e IA — e aprova o que a IA propõe nesses módulos (invoice e QuickBooks ficam com o gerente)',
  VIEWER: 'só leitura',
}

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
  // conta de acesso livre (dono, 17/09): não tem cargo e ninguém muda
  if (u.free) return <Chip tone="accent" title="Opera em todas as áreas; não tem cargo">Acesso livre</Chip>
  if (self) return <Chip tone="accent">{ROLE_PT[u.role] || u.role}</Chip>
  if (!open) return <button className="chip accent" style={{ cursor: 'pointer', border: '1px dashed var(--accent)' }} title="Clique para mudar o nível de acesso" onClick={() => setOpen(true)}>{ROLE_PT[u.role] || u.role} ▾</button>
  return <span className="row"><select className="input" style={{ width: 160, padding: '4px 8px' }} autoFocus disabled={busy} value={u.role} onChange={e => mudar(e.target.value)} onBlur={() => !busy && setOpen(false)}>
    {['ADMIN', 'MANAGER', 'OPERATOR', 'VIEWER'].map(r => <option key={r} value={r}>{ROLE_PT[r]}</option>)}</select>{busy && <Spinner />}</span>
}

// ------------------------------------------------------------------ chaves de API
// Dono, 21/09: "preciso montar uma chave api desse command center". A chave aparece UMA vez,
// na criação — depois só existe o hash no banco. A tela diz isso antes de o valor sumir.
interface K {
  id: string; name: string; role: string; created_at: string; expires_at: string | null
  last_used_at: string | null; last_ip: string | null; uses: number; revoked_at: string | null
  note: string | null; como: string; como_nome: string; papel_pessoa: string; criada_por: string | null
  read_only: number
}

function Chaves({ usuarios }: { usuarios: U[] }) {
  const { user } = useAuth()
  const toast = useToast()
  const perguntar = usePerguntar()
  const { data, error, loading, reload } = useGet<K[]>('/keys')
  const [f, setF] = useState({ name: '', role: 'VIEWER', user_id: '', days: '', note: '', read_only: true })
  const [nova, setNova] = useState<{ id: string; chave: string; read_only: boolean } | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  async function criar(e: FormEvent) {
    e.preventDefault(); setBusy(true); setErr(null)
    try {
      const r = await api.post<{ id: string; chave: string; read_only: boolean }>('/keys', {
        name: f.name, role: f.role, note: f.note || null, read_only: f.read_only,
        user_id: f.user_id ? Number(f.user_id) : null,
        days: f.days ? Number(f.days) : null,
      })
      setNova(r); setF({ name: '', role: 'VIEWER', user_id: '', days: '', note: '', read_only: true }); reload()
    } catch (ex) { setErr((ex as ApiError).message) } finally { setBusy(false) }
  }
  async function revogar(k: K) {
    if (!await perguntar({
      titulo: `Revogar a chave "${k.name}"?`,
      texto: 'Quem estiver usando esta chave recebe erro no pedido seguinte. Não dá para desfazer: crie outra.',
      ok: 'Revogar', perigo: true,
    })) return
    try { await api.post(`/keys/${k.id}/revoke`); toast('Chave revogada.', 'ok'); reload() }
    catch (ex) { toast((ex as ApiError).message, 'crit') }
  }

  const eu = usuarios.find(x => x.id === user?.id)
  const tetoDe = (id: string) => usuarios.find(x => String(x.id) === id)?.role
  return <Section title="Chaves de API" count={(data || []).filter(k => !k.revoked_at).length}>
    {nova && <Banner tone={nova.read_only ? 'ok' : 'warn'}>
      <div><b>Guarde agora: esta é a única vez que a chave aparece.</b> Ela não fica no banco — só o resumo dela.
        Se perder, revogue esta e crie outra.</div>
      <div className="small" style={{ marginTop: 4 }}>{nova.read_only
        ? 'Esta chave consulta o painel e não muda nada.'
        : 'Atenção: esta chave ESCREVE. O que ela fizer acontece de verdade — mensagem sai para o cliente, preço muda no QuickBooks — sem passar por aprovação.'}</div>
      <div className="row wrap" style={{ marginTop: 8 }}>
        <code className="mono small" style={{ wordBreak: 'break-all' }}>{nova.chave}</code>
        <button className="btn sm" onClick={() => navigator.clipboard?.writeText(nova.chave).then(() => toast('Chave copiada.', 'ok'))}>copiar</button>
        <button className="btn sm" onClick={() => setNova(null)}>já guardei</button>
      </div></Banner>}
    <div className="grid" style={{ gridTemplateColumns: 'minmax(0,1fr) 320px' }}>
      <div>
        {error && !data ? <ErrorState error={error} retry={reload} /> : loading && !data ? <Loading /> :
          (data || []).length === 0 ? <Empty>Nenhuma chave criada. O painel só responde a quem tem sessão.</Empty> :
            <div className="tbl-wrap"><table className="tbl"><thead><tr>
              <th>Nome</th><th>Papel</th><th>Age como</th><th>Último uso</th><th>Validade</th><th></th></tr></thead><tbody>
              {(data || []).map(k => <tr key={k.id} style={k.revoked_at ? { opacity: .5 } : undefined}>
                <td><div>{k.name}</div><div className="mono small muted">urk_{k.id}_…{k.note ? ` · ${k.note}` : ''}</div></td>
                <td>{k.revoked_at ? <Chip tone="neutral">revogada</Chip> : <div className="row wrap" style={{ gap: 4 }}>
                  <Chip tone={k.role === 'VIEWER' ? 'neutral' : 'accent'}>{ROLE_PT[k.role] || k.role}</Chip>
                  {k.read_only ? <Chip tone="ok" title="Consulta e não muda nada">só leitura</Chip>
                    : <Chip tone="warn" title="O que esta chave fizer acontece de verdade, sem aprovação">escreve</Chip>}</div>}</td>
                <td className="small">{k.como_nome}<div className="muted">{k.como}</div></td>
                <td className="small">{k.last_used_at ? <>{fmtDateTime(k.last_used_at)}<div className="muted">{k.uses} uso(s){k.last_ip ? ` · ${k.last_ip}` : ''}</div></> : <span className="muted">nunca usada</span>}</td>
                <td className="small">{k.expires_at ? fmtDateTime(k.expires_at) : <span className="muted">não expira</span>}</td>
                <td>{!k.revoked_at && <button className="btn sm danger" onClick={() => revogar(k)}>Revogar</button>}</td></tr>)}
            </tbody></table></div>}
      </div>
      <form className="stack" onSubmit={criar}>
        {err && <Banner tone="crit">{err}</Banner>}
        <div className="field"><label>Para que serve</label>
          <input className="input" required placeholder="n8n — leitura do painel" value={f.name} onChange={e => setF({ ...f, name: e.target.value })} /></div>
        <div className="field"><label>Papel</label>
          <select className="input" value={f.role} onChange={e => setF({ ...f, role: e.target.value })}>
            {['VIEWER', 'OPERATOR', 'MANAGER', 'ADMIN'].map(r => <option key={r} value={r}>{ROLE_PT[r]}</option>)}</select>
          <span className="small muted">{ROLE_O_QUE[f.role]}</span></div>
        <div className="field"><label>Age como</label>
          <select className="input" value={f.user_id} onChange={e => setF({ ...f, user_id: e.target.value })}>
            <option value="">{eu ? `${eu.name} (você)` : 'você'}</option>
            {usuarios.filter(x => x.id !== user?.id && x.active).map(x => <option key={x.id} value={x.id}>{x.name} — {ROLE_PT[x.role] || x.role}</option>)}</select>
          <span className="small muted">A chave nunca alcança mais do que esta pessoa alcança{f.user_id && tetoDe(f.user_id) ? ` (${ROLE_PT[tetoDe(f.user_id)!]})` : ''}. Rebaixou a pessoa, a chave desce junto.</span></div>
        <div className="field"><label>O que ela pode fazer</label>
          <label className="row" style={{ gap: 8, cursor: 'pointer' }}>
            <input type="checkbox" checked={f.read_only} onChange={e => setF({ ...f, read_only: e.target.checked })} />
            <span className="small">Só leitura — consulta e não muda nada</span></label>
          {!f.read_only && <span className="small" style={{ color: 'var(--warn)' }}>
            Esta chave vai ESCREVER: mensagem sai para o cliente, preço muda no QuickBooks, tudo sem passar por aprovação.
            Papel e escrita são coisas separadas de propósito — dê escrita só se for mesmo necessário.</span>}</div>
        <div className="field"><label>Validade (dias)</label>
          <input className="input" type="number" min={1} placeholder="em branco = não expira" value={f.days} onChange={e => setF({ ...f, days: e.target.value })} /></div>
        <div className="field"><label>Anotação</label>
          <input className="input" placeholder="opcional: quem pediu, onde está usada" value={f.note} onChange={e => setF({ ...f, note: e.target.value })} /></div>
        <button className="btn primary" disabled={busy || !f.name.trim()}>{busy ? <Spinner /> : 'Criar chave'}</button>
        <div className="small muted">Use em <code className="mono">Authorization: Bearer urk_…</code> ou <code className="mono">X-API-Key: urk_…</code>. Chave não precisa de CSRF e não abre sessão.</div>
      </form>
    </div>
    <ComoUsar />
  </Section>
}

/** O passo a passo fica AQUI, junto de onde a chave nasce (dono, 21/09: "deixe o passo a
 *  passo na mesma sessão das apis") — e não num documento que ninguém abre na hora. */
function ComoUsar() {
  const toast = useToast()
  const base = typeof window !== 'undefined' ? window.location.origin : 'https://urace-bridge.duckdns.org'
  const curl = `curl -s -H "Authorization: Bearer SUA_CHAVE" ${base}/ops/api/dashboard`
  const prova = `curl -s -o /dev/null -w "%{http_code}\n" -X POST -H "Authorization: Bearer SUA_CHAVE" -H "Content-Type: application/json" -d '{"name":"teste"}' ${base}/ops/api/clients`
  const mcp = `claude mcp add urace-cc --env CC_API_KEY=SUA_CHAVE --env CC_URL=${base} -- /home/ubuntu/.urace/cc-venv/bin/python /home/ubuntu/Uraceagent/adminai/mcp/command_center_mcp.py`
  const Linha = ({ cmd, rotulo }: { cmd: string; rotulo: string }) =>
    <div className="row wrap" style={{ gap: 8, marginTop: 6, alignItems: 'flex-start' }}>
      <code className="mono small" style={{ wordBreak: 'break-all', flex: '1 1 320px' }}>{cmd}</code>
      <button className="btn sm" onClick={() => navigator.clipboard?.writeText(cmd).then(() => toast(`${rotulo} copiado.`, 'ok'))}>copiar</button>
    </div>

  return <details style={{ marginTop: 14 }}>
    <summary style={{ cursor: 'pointer' }}><b>Como usar a chave</b> <span className="small muted">— script, agente de IA e o que fazer se vazar</span></summary>
    <div className="stack" style={{ gap: 14, marginTop: 10 }}>
      <div className="card" style={{ padding: '12px 14px' }}>
        <b>1. Em script, integração ou terminal</b>
        <div className="small ink2">A chave vai no cabeçalho. Serve <code className="mono">Authorization: Bearer</code> ou <code className="mono">X-API-Key</code>. Não precisa de CSRF e não abre sessão.</div>
        <Linha cmd={curl} rotulo="Comando" />
        <div className="small muted" style={{ marginTop: 6 }}>Voltou JSON com os números do dia? Funcionando.</div>
      </div>

      <div className="card" style={{ padding: '12px 14px' }}>
        <b>2. Confira que ela não escreve</b>
        <div className="small ink2">Com "só leitura" marcado, isto tem que responder <b>403</b>. Se responder 200, a chave está escrevendo — revogue e crie outra.</div>
        <Linha cmd={prova} rotulo="Comando" />
      </div>

      <div className="card" style={{ padding: '12px 14px' }}>
        <b>3. Ligar num Claude (MCP)</b>
        <div className="small ink2">Um Claude não usa a chave crua: ele fala MCP. O servidor <code className="mono">command_center_mcp.py</code> traduz o painel em ferramentas
          (<span className="mono">cc_dashboard</span>, <span className="mono">cc_atencao</span>, <span className="mono">cc_invoices</span>, <span className="mono">cc_financeiro</span>, <span className="mono">cc_conversas</span>, <span className="mono">cc_auditoria</span>…).
          Rode este comando <b>na máquina onde o Claude roda</b>:</div>
        <Linha cmd={mcp} rotulo="Comando" />
        <div className="small muted" style={{ marginTop: 6 }}>Nenhuma ferramenta desse servidor escreve — ele não sabe fazer outro verbo além de GET. Vale para o Claude Code e para qualquer agente que aceite MCP por stdio; o claude.ai (web/app) pede conector remoto com OAuth, que é outro caminho.</div>
      </div>

      <div className="card" style={{ padding: '12px 14px' }}>
        <b>4. Se a chave vazar</b>
        <div className="small ink2">Revogue aqui — corta na hora, o pedido seguinte já recebe erro — e crie outra. Não existe "trocar o segredo": a identidade da chave é o segredo.
          O <span className="mono">urk_&lt;id&gt;</span> que aparece na lista é público de propósito (vai no log e na auditoria) e sozinho não abre nada.</div>
      </div>
    </div>
  </details>
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
  // 21/09: quem esquece a senha não tem como provar a antiga. O administrador define uma nova,
  // fica na auditoria, e as sessões abertas daquela pessoa caem na hora.
  async function senha(u: U) {
    const nova = await perguntar({
      titulo: `Definir uma senha nova para ${u.name}`,
      texto: `${u.email} entra com a senha que você digitar aqui. As sessões abertas dela caem na hora. Mínimo 5 caracteres — combine a senha com a pessoa por fora do painel.`,
      campo: 'Senha nova', segredo: true, ok: 'Definir senha',
    })
    if (typeof nova !== 'string' || !nova) return
    try { await api.post(`/users/${u.id}/password`, { password: nova }); toast(`Senha definida para ${u.email}.`, 'ok'); reload() }
    catch (ex) { toast((ex as ApiError).message, 'crit') }
  }
  return <>
    <PageHeader title="Usuários" help={<>Administrador: {ROLE_O_QUE.ADMIN}. Gerente: {ROLE_O_QUE.MANAGER}. Operador: {ROLE_O_QUE.OPERATOR}. Leitura: {ROLE_O_QUE.VIEWER}. Conta de acesso livre não tem cargo e alcança tudo.</>} />
    <div className="grid" style={{ gridTemplateColumns: 'minmax(0,1fr) 320px' }}>
      <Section title="Cadastrados" count={data?.length} tight>
        {error && !data ? <ErrorState error={error} retry={reload} /> : loading && !data ? <Loading /> :
          <div className="tbl-wrap"><table className="tbl"><thead><tr><th>Nome</th><th>E-mail</th><th>Papel</th><th>Ativo</th><th>Último login</th><th></th></tr></thead><tbody>
            {(data || []).map(u => <tr key={u.id}><td>{u.name}</td><td className="small">{u.email}</td><td><PapelEditavel u={u} self={u.id === user?.id} onChanged={reload} /></td><td>{u.active ? <Chip tone="ok">sim</Chip> : <Chip tone="neutral">não</Chip>}</td><td className="small nowrap">{u.last_login_at
                ? <><span className="mono">{fmtDateTime(u.last_login_at)}</span><div className="muted">{ago(u.last_login_at)}</div></>
                : <span className="muted">nunca entrou</span>}</td>
              <td><div className="row wrap" style={{ gap: 6, justifyContent: 'flex-end' }}>
                <button className="btn sm" onClick={() => senha(u)} title="Definir uma senha nova para esta pessoa">Definir senha</button>
                {u.id !== user?.id && <button className="btn sm" onClick={() => toggle(u)}>{u.active ? 'Desativar' : 'Reativar'}</button>}
              </div></td></tr>)}
          </tbody></table></div>}
      </Section>
      <Section title="Novo usuário"><form className="stack" onSubmit={create}>
        {err && <Banner tone="crit">{err}</Banner>}
        <div className="field"><label>Nome</label><input className="input" required value={f.name} onChange={e => setF({ ...f, name: e.target.value })} /></div>
        <div className="field"><label>E-mail</label><input className="input" type="email" required value={f.email} onChange={e => setF({ ...f, email: e.target.value })} /></div>
        <div className="field"><label>Papel</label><select className="input" value={f.role} onChange={e => setF({ ...f, role: e.target.value })}>{['ADMIN', 'MANAGER', 'OPERATOR', 'VIEWER'].map(r => <option key={r} value={r}>{ROLE_PT[r]}</option>)}</select>
          <span className="small muted">{ROLE_O_QUE[f.role]}</span></div>
        <div className="field"><label>Senha inicial</label><input className="input" type="password" required minLength={5} autoComplete="new-password" value={f.password} onChange={e => setF({ ...f, password: e.target.value })} /><span className="small muted">Mínimo 5 caracteres. Peça para trocar no primeiro acesso.</span></div>
        <button className="btn primary" disabled={busy}>{busy ? <Spinner /> : 'Criar'}</button>
      </form></Section>
    </div>
    <Chaves usuarios={data || []} />
  </>
}

export function Audit() {
  const { data, error, loading, reload } = useGet<AuditRow[]>('/audit?limit=300')
  const [q, setQ] = useState('')
  const rows = (data || []).filter(r => !q || `${r.event} ${r.actor} ${r.entity_type} ${r.entity_id} ${r.detail}`.toLowerCase().includes(q.toLowerCase()))
  return <>
    <PageHeader title="Auditoria" help={<>Registro imutável (gatilhos no banco impedem UPDATE/DELETE). Logins, comandos, decisões, mudanças de política.</>}>
      <input className="input" style={{ width: 260 }} placeholder="Filtrar" value={q} onChange={e => setQ(e.target.value)} /><button className="btn" onClick={reload}>↻</button></PageHeader>
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
    <PageHeader title="Minha conta" help={<>{user?.name} · {user?.email} · {user?.free ? 'acesso livre (sem cargo)' : ROLE_PT[user?.role || ''] || user?.role}</>} />
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
