/* O que a IA pode fazer — lido do código (ferramentas dos MCPs), da tabela de políticas, das ações
   do painel e das regras de automação. Nunca desatualiza: se entrar ferramenta nova, aparece aqui. */
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useGet } from '../api/hooks'
import { Chip, Empty, ErrorState, Loading, PageHeader, Section, Status, SYS_NAME } from '../components/ui'
import { fmtDateTime } from '../components/fmt'
import { tr } from '../i18n'

interface Tool { system: string; name: string; description: string; kind: 'leitura' | 'escrita' | 'erro'; policy: string | null; note?: string | null; classified?: boolean }
interface Rule { name: string; enabled: number; trigger: string; schedule: string | null; last_run_at: string | null; last_result: string | null }
interface Cap { tools: Tool[]; blocked: { name: string; note: string | null }[]; rules: Rule[]; human_only: { area: string; what: string }[] }

const POL: Record<string, [string, 'ok' | 'wait' | 'warn' | 'crit']> = { SAFE: ['sozinha', 'ok'], REQUIRES_CONFIRMATION: [tr("com confirmação"), 'wait'], REQUIRES_APPROVAL: [tr("com aprovação"), 'warn'], BLOCKED: ['bloqueada', 'crit'] }
const RULE_PT: Record<string, string> = {
  novo_servico: tr("Serviço novo no quadro"), email_cliente: tr("E-mail de cliente conhecido"), waiver_devolvida: tr("Waiver com e-mail devolvido"), pagamento_confirmado: tr("Pagamento confirmado"),
  waiver_na_tarefa: tr("Waiver junto da tarefa"), waiver_assinada: tr("Waiver assinada"), mensalidade_dia_1: tr("Mensalidade no dia 1"), tarefa_vencida: tr("Serviço vencido no quadro"),
  gmail_triagem: tr("Triagem do Gmail"), sondagem_integracoes: tr("Sondagem das integrações"), lembrete_invoice: tr("Lembretes de invoice"), varredura_clientes: tr("Varredura dos clientes (Gmail + DocuSign)"),
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
    <PageHeader title={tr("O que a IA pode fazer")} help={tr("Lido direto do código e da tabela de políticas: cada ferramenta registrada nos MCPs, as ações do painel, as regras de automação e o que só a mão humana faz. Se entrar ferramenta nova, aparece aqui sozinha.")}>
      <input className="input" style={{ width: 240 }} placeholder={tr("Buscar ferramenta…")} value={q} onChange={e => setQ(e.target.value)} aria-label={tr("Buscar")} />
      <select className="input" style={{ width: 150 }} value={so} onChange={e => setSo(e.target.value as 'all')} aria-label={tr("Tipo")}><option value="all">{tr("Tudo")}</option><option value="leitura">{tr("Só leitura")}</option><option value="escrita">{tr("Só escrita")}</option></select>
    </PageHeader>
    <div className="strip">
      <div className="it"><span className="lbl">{tr("Ferramentas")}</span><span className="val">{data.tools.length}</span></div>
      <div className="it"><span className="lbl">{tr("Leitura")}</span><span className="val">{data.tools.filter(t => t.kind === 'leitura').length}</span></div>
      <div className="it"><span className="lbl">{tr("Sozinha")}</span><span className="val ok">{n('SAFE')}</span></div>
      <div className="it"><span className="lbl">{tr("Com confirmação")}</span><span className="val">{n('REQUIRES_CONFIRMATION')}</span></div>
      <div className="it"><span className="lbl">{tr("Com aprovação")}</span><span className="val warn">{n('REQUIRES_APPROVAL')}</span></div>
      <div className="it"><span className="lbl">{tr("Bloqueadas")}</span><span className="val crit">{data.blocked.length}</span></div>
    </div>
    <div className="small muted">{tr("Leitura é sempre livre. Escrita segue a política:")} <b>{tr("sozinha")}</b> {tr("executa na hora ·")} <b>{tr("com confirmação")}</b> {tr("a IA pergunta antes ·")} <b>{tr("com aprovação")}</b> {tr("espera um gerente em")} <Link to="/approvals">{tr("Aprovações")}</Link> {tr("(é o que sai da empresa: invoice, waiver, e-mail) ·")} <b>{tr("bloqueada")}</b> {tr("nunca. Quem muda a política é o administrador, em")} <Link to="/policies">{tr("Políticas da IA")}</Link>.</div>
    {porSistema.length === 0 && <Empty>{tr("Nada bate com a busca.")}</Empty>}
    {porSistema.map(([s, ts]) => <Section key={s} title={s === 'painel' ? tr("Ações do painel") : SYS_NAME[s] || s} count={ts.length} tight>
      <div className="tbl-wrap"><table className="tbl"><thead><tr><th>{tr("Ferramenta")}</th><th>{tr("O que faz")}</th><th>{tr("Como age")}</th></tr></thead><tbody>
        {ts.map(t => <tr key={t.name}><td className="mono small nowrap" style={{ verticalAlign: 'top' }}>{t.name}</td><td className="small ink2" style={{ maxWidth: 640 }}>{t.description}{t.note && <div className="small muted">{tr("política:")} {t.note}</div>}</td>
          <td className="nowrap">{t.kind === 'leitura' ? <Chip tone="neutral" glyph="●">{tr("leitura")}</Chip> : <Status kind={POL[t.policy || '']?.[1] || 'wait'} label={POL[t.policy || '']?.[0] || t.policy} />}{t.kind === 'escrita' && !t.classified && <div className="small muted">{tr("sem política: pede confirmação")}</div>}</td></tr>)}
      </tbody></table></div>
    </Section>)}
    <div className="grid g2">
      <Section title={tr("Bloqueado para a IA")} count={data.blocked.length} tight>
        <div className="tbl-wrap"><table className="tbl"><tbody>{data.blocked.map(b => <tr key={b.name}><td className="mono small">{b.name}</td><td className="small ink2">{b.note}</td></tr>)}</tbody></table></div>
      </Section>
      <Section title={tr("Só pela mão humana")} count={data.human_only.length} tight>
        <div className="tbl-wrap"><table className="tbl"><tbody>{data.human_only.map(h => <tr key={h.area}><td><b>{h.area}</b></td><td className="small ink2">{h.what}</td></tr>)}</tbody></table></div>
      </Section>
    </div>
    <Section title={tr("Rotinas automáticas")} count={data.rules.length} tight right={<Link to="/automation" className="small">{tr("ligar/desligar →")}</Link>}>
      <div className="tbl-wrap"><table className="tbl"><thead><tr><th>{tr("Regra")}</th><th>{tr("Quando")}</th><th>{tr("Estado")}</th><th>{tr("Última")}</th></tr></thead><tbody>
        {data.rules.map(r => { let hs = ''; try { hs = (JSON.parse(r.schedule || '[]') as string[]).join(' · ') } catch { hs = r.schedule || '' } return <tr key={r.name}><td><b>{RULE_PT[r.name] || r.name}</b><div className="small muted mono">{r.name}</div></td><td className="small">{hs ? tr("às {0}", hs) : tr("quando o evento acontece")}</td><td><Status kind={r.enabled ? 'ok' : 'off'} label={r.enabled ? tr("ligada") : tr("desligada")} /></td><td className="small muted mono">{r.last_run_at ? fmtDateTime(r.last_run_at.replace(' ', 'T')) : '—'}</td></tr> })}
      </tbody></table></div>
    </Section>
  </>
}
