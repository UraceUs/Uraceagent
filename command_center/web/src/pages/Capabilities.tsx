/* O que a IA pode fazer — lido do código (ferramentas dos MCPs), da tabela de políticas, das ações
   do painel e das regras de automação. Nunca desatualiza: se entrar ferramenta nova, aparece aqui. */
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useGet } from '../api/hooks'
import { Chip, Empty, ErrorState, Loading, PageHeader, Section, Status, SYS_NAME } from '../components/ui'
import { fmtDateTime } from '../components/fmt'

interface Tool { system: string; name: string; description: string; kind: 'leitura' | 'escrita' | 'erro'; policy: string | null; note?: string | null; classified?: boolean }
interface Rule { name: string; enabled: number; trigger: string; schedule: string | null; last_run_at: string | null; last_result: string | null }
interface Cap { tools: Tool[]; blocked: { name: string; note: string | null }[]; rules: Rule[]; human_only: { area: string; what: string }[] }

const POL: Record<string, [string, 'ok' | 'wait' | 'warn' | 'crit']> = { SAFE: ['sozinha', 'ok'], REQUIRES_CONFIRMATION: ['com confirmação', 'wait'], REQUIRES_APPROVAL: ['com aprovação', 'warn'], BLOCKED: ['bloqueada', 'crit'] }
const RULE_PT: Record<string, string> = {
  novo_servico: 'Serviço novo no quadro', email_cliente: 'E-mail de cliente conhecido', waiver_devolvida: 'Waiver com e-mail devolvido', pagamento_confirmado: 'Pagamento confirmado',
  waiver_na_tarefa: 'Waiver junto da tarefa', waiver_assinada: 'Waiver assinada', mensalidade_dia_1: 'Mensalidade no dia 1', tarefa_vencida: 'Serviço vencido no quadro',
  gmail_triagem: 'Triagem do Gmail', sondagem_integracoes: 'Sondagem das integrações', lembrete_invoice: 'Lembretes de invoice', varredura_clientes: 'Varredura dos clientes (Gmail + DocuSign)',
}
const ORDEM = ['asana', 'docusign', 'gmail', 'quickbooks', 'kommo', 'painel']

export function Capabilities() {
  const { data, error, loading, reload } = useGet<Cap>('/ai/capabilities', 120000)
  const [q, setQ] = useState('')
  const [so, setSo] = useState<'all' | 'leitura' | 'escrita'>('all')
  if (error && !data) return <ErrorState error={error} retry={reload} />
  if (loading && !data) return <Loading rows={8} />
  if (!data) return null
  const qn = q.trim().toLowerCase()
  const tools = data.tools.filter(t => (so === 'all' || t.kind === so) && (!qn || `${t.name} ${t.description} ${t.system}`.toLowerCase().includes(qn)))
  const porSistema = ORDEM.filter(s => tools.some(t => t.system === s)).map(s => [s, tools.filter(t => t.system === s)] as const)
  const n = (k: string) => data.tools.filter(t => t.kind === 'escrita' && t.policy === k).length
  return <>
    <PageHeader title="O que a IA pode fazer" help="Lido direto do código e da tabela de políticas: cada ferramenta registrada nos MCPs, as ações do painel, as regras de automação e o que só a mão humana faz. Se entrar ferramenta nova, aparece aqui sozinha.">
      <input className="input" style={{ width: 240 }} placeholder="Buscar ferramenta…" value={q} onChange={e => setQ(e.target.value)} aria-label="Buscar" />
      <select className="input" style={{ width: 150 }} value={so} onChange={e => setSo(e.target.value as 'all')} aria-label="Tipo"><option value="all">Tudo</option><option value="leitura">Só leitura</option><option value="escrita">Só escrita</option></select>
    </PageHeader>
    <div className="strip">
      <div className="it"><span className="lbl">Ferramentas</span><span className="val">{data.tools.length}</span></div>
      <div className="it"><span className="lbl">Leitura</span><span className="val">{data.tools.filter(t => t.kind === 'leitura').length}</span></div>
      <div className="it"><span className="lbl">Sozinha</span><span className="val ok">{n('SAFE')}</span></div>
      <div className="it"><span className="lbl">Com confirmação</span><span className="val">{n('REQUIRES_CONFIRMATION')}</span></div>
      <div className="it"><span className="lbl">Com aprovação</span><span className="val warn">{n('REQUIRES_APPROVAL')}</span></div>
      <div className="it"><span className="lbl">Bloqueadas</span><span className="val crit">{data.blocked.length}</span></div>
    </div>
    <div className="small muted">Leitura é sempre livre. Escrita segue a política: <b>sozinha</b> executa na hora · <b>com confirmação</b> a IA pergunta antes · <b>com aprovação</b> espera um gerente em <Link to="/approvals">Aprovações</Link> (é o que sai da empresa: invoice, waiver, e-mail) · <b>bloqueada</b> nunca. Quem muda a política é o administrador, em <Link to="/policies">Políticas da IA</Link>.</div>
    {porSistema.length === 0 && <Empty>Nada bate com a busca.</Empty>}
    {porSistema.map(([s, ts]) => <Section key={s} title={s === 'painel' ? 'Ações do painel' : SYS_NAME[s] || s} count={ts.length} tight>
      <div className="tbl-wrap"><table className="tbl"><thead><tr><th>Ferramenta</th><th>O que faz</th><th>Como age</th></tr></thead><tbody>
        {ts.map(t => <tr key={t.name}><td className="mono small nowrap" style={{ verticalAlign: 'top' }}>{t.name}</td><td className="small ink2" style={{ maxWidth: 640 }}>{t.description}{t.note && <div className="small muted">política: {t.note}</div>}</td>
          <td className="nowrap">{t.kind === 'leitura' ? <Chip tone="neutral" glyph="●">leitura</Chip> : <Status kind={POL[t.policy || '']?.[1] || 'wait'} label={POL[t.policy || '']?.[0] || t.policy} />}{t.kind === 'escrita' && !t.classified && <div className="small muted">sem política: pede confirmação</div>}</td></tr>)}
      </tbody></table></div>
    </Section>)}
    <div className="grid g2">
      <Section title="Bloqueado para a IA" count={data.blocked.length} tight>
        <div className="tbl-wrap"><table className="tbl"><tbody>{data.blocked.map(b => <tr key={b.name}><td className="mono small">{b.name}</td><td className="small ink2">{b.note}</td></tr>)}</tbody></table></div>
      </Section>
      <Section title="Só pela mão humana" count={data.human_only.length} tight>
        <div className="tbl-wrap"><table className="tbl"><tbody>{data.human_only.map(h => <tr key={h.area}><td><b>{h.area}</b></td><td className="small ink2">{h.what}</td></tr>)}</tbody></table></div>
      </Section>
    </div>
    <Section title="Rotinas automáticas" count={data.rules.length} tight right={<Link to="/automation" className="small">ligar/desligar →</Link>}>
      <div className="tbl-wrap"><table className="tbl"><thead><tr><th>Regra</th><th>Quando</th><th>Estado</th><th>Última</th></tr></thead><tbody>
        {data.rules.map(r => { let hs = ''; try { hs = (JSON.parse(r.schedule || '[]') as string[]).join(' · ') } catch { hs = r.schedule || '' } return <tr key={r.name}><td><b>{RULE_PT[r.name] || r.name}</b><div className="small muted mono">{r.name}</div></td><td className="small">{hs ? `às ${hs}` : 'quando o evento acontece'}</td><td><Status kind={r.enabled ? 'ok' : 'off'} label={r.enabled ? 'ligada' : 'desligada'} /></td><td className="small muted mono">{r.last_run_at ? fmtDateTime(r.last_run_at.replace(' ', 'T')) : '—'}</td></tr> })}
      </tbody></table></div>
    </Section>
  </>
}
