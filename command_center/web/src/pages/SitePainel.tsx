/* O painel do site (#306): as métricas do site público num lugar só.
 * Dono, 16/10: "uma sessão dedicada exclusiva somente para o site … E aí também do site um dashboard com as métricas
 * dele". Tudo vem do sistema (pedidos no Stripe, planos, agendamentos, contas, oportunidades, campanhas) e das
 * visitas contadas no servidor, sem IP nem cookie. O que ainda não tem dado aparece como "sem dado", nunca inventado. */
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useGet } from '../api/hooks'
import { Empty, ErrorState, Kpi, Loading, Section, Strip } from '../components/ui'
import { fmtDate, fmtDateTime, money } from '../components/fmt'
import { tr, LOCALE } from '../i18n'

interface Conta { nome: string; qtd: number; receita: number }
interface Dia { dia: string; receita: number; pedidos: number; visitas: number }
interface Pagamento { foram: number; pago: number; aguardando: number; falhou: number; expirado: number; aberto: number; conversao: number | null }
interface Painel {
  periodo: { dias: number; de: string; ate: string; anterior: [string, string] }
  vendas: { receita: number; receita_ant: number; loja_e_carrinho: number; planos: number; sessoes_invoice: number; pedidos_pagos: number
    pedidos_pagos_ant: number; planos_pagos: number; sessoes_pagas_invoice: number; deposito: number; ticket_medio: number | null }
  pagamento: { carrinho: Pagamento; buy_now: Pagamento; funil: { etapa: 'carrinho' | 'checkout' | 'pago'; n: number }[] }
  sessoes: { marcadas: number; canceladas: number; pelo_site: number; pela_area: number; proximas: number; pendentes: number }
  contas: { novas: number; sem_vinculo: number }
  leads: { novos: number; ganhos: number; perdidos: number }
  produtos: Conta[]; servicos: Conta[]
  campanhas: { com_campanha: { fonte: string; n: number }[]; sem_campanha: number }
  visitas: { total: number; total_ant: number | null; entradas: number; carrinho: number; desde: string | null; parcial: boolean
    paginas: { caminho: string; n: number }[]; fontes: { fonte: string; n: number }[] }
  dias: Dia[]
  atencao: { pedidos_sem_vaga: number; avisos_falharam: number; agendamentos_pendentes: number; contas_sem_vinculo: number; janela_dias: number }
  saude: { desde: string; paginas: { n: number; erros_5xx: number; p95_ms: number | null }; compra: { n: number; erros_5xx: number; p95_ms: number | null } }
}

const ETAPA: Record<Painel['pagamento']['funil'][number]['etapa'], string> = {
  carrinho: tr("Abriram o carrinho"), checkout: tr("Foram ao pagamento (Stripe)"), pago: tr("Pagaram"),
}
const FONTE: Record<string, string> = { direto: tr("Direto (digitou ou favorito)"), google: tr("Google"), instagram: tr("Instagram"),
  facebook: tr("Facebook"), gmail: tr("E-mail (Gmail)"), app: tr("Um app do celular"), 'outro site': tr("Outro site"), outros: tr("Outras fontes") }

/** "+12% vs. os 30 dias antes" (ou "sem base", quando o período anterior não tem com o que comparar). */
function comparado(agora: number, antes: number | null, dias: number) {
  if (antes === null) return tr("sem base no período anterior")
  if (!antes) return agora ? tr("sem base no período anterior") : null
  const p = Math.round(100 * (agora - antes) / antes)
  return tr("{0}{1}% vs. os {2} dias antes", p > 0 ? '+' : '', p, dias)
}

/** Barras por dia, em SVG puro (sem biblioteca). A descrição em texto vai no `aria-label`; cada barra tem o valor no `title`. */
function Barras({ dias, campo, rotulo, valor }: { dias: Dia[]; campo: 'receita' | 'visitas' | 'pedidos'; rotulo: string; valor: (v: number) => string }) {
  const max = Math.max(...dias.map(d => d[campo]), 0)
  const total = dias.reduce((s, d) => s + d[campo], 0)
  const W = 600, H = 120, gap = dias.length > 40 ? 1 : 2, w = (W - gap * (dias.length - 1)) / dias.length
  const melhor = dias.reduce<Dia | null>((m, d) => !m || d[campo] > m[campo] ? d : m, null)
  const resumo = max ? tr("{0}: {1} no período; o melhor dia foi {2} ({3}).", rotulo, valor(total), fmtDate(melhor!.dia), valor(melhor![campo]))
    : tr("{0}: nada no período.", rotulo)
  return <figure className="sp-barras">
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" aria-label={resumo}>
      {dias.map((d, i) => {
        const h = max ? Math.max(d[campo] ? 2 : 0, Math.round((H - 4) * d[campo] / max)) : 0
        return <rect key={d.dia} x={i * (w + gap)} y={H - h} width={w} height={h} rx={w > 6 ? 2 : 0}><title>{`${fmtDate(d.dia)}: ${valor(d[campo])}`}</title></rect>
      })}
    </svg>
    <figcaption className="small muted row"><span>{fmtDate(dias[0]?.dia)}</span><span className="grow" /><span>{fmtDate(dias[dias.length - 1]?.dia)}</span></figcaption>
  </figure>
}

/** Lista "nome · barra · número" (os mais vendidos, as páginas, as fontes). */
function Ranking({ itens, vazio }: { itens: { rotulo: string; n: number; extra?: string }[]; vazio: string }) {
  if (!itens.length) return <p className="small muted" style={{ margin: 0 }}>{vazio}</p>
  const max = Math.max(...itens.map(i => i.n), 1)
  return <ol className="sp-rank">{itens.map(i => <li key={i.rotulo}>
    <span className="sp-rank-nome">{i.rotulo}</span>
    <span className="sp-rank-barra" aria-hidden="true"><i style={{ transform: `scaleX(${i.n / max})` }} /></span>
    <b className="mono">{i.n.toLocaleString(LOCALE())}</b>{i.extra && <span className="small muted mono">{i.extra}</span>}
  </li>)}</ol>
}

export function SitePainel() {
  const [dias, setDias] = useState(30)
  const l = useGet<Painel>(`/site/painel?dias=${dias}`, 60000)
  const p = l.data
  const n = (v: number) => v.toLocaleString(LOCALE())
  const foram = p ? p.pagamento.carrinho.foram + p.pagamento.buy_now.foram : 0
  const pagaram = p ? p.pagamento.carrinho.pago + p.pagamento.buy_now.pago : 0
  return <div className="stack" style={{ gap: 14 }}>
    <div className="seg" role="group" aria-label={tr("Período")}>{[7, 30, 90].map(d =>
      <button key={d} className={`btn sm${dias === d ? '' : ' ghost'}`} aria-pressed={dias === d} onClick={() => setDias(d)}>{tr("Últimos {0} dias", d)}</button>)}</div>
    {l.error && <ErrorState error={l.error} retry={l.reload} />}
    {l.loading && !p && <Loading />}
    {p && <>
      <p className="small muted" style={{ margin: 0 }}>{tr("De {0} a {1}, no horário da Flórida.", fmtDate(p.periodo.de), fmtDate(p.periodo.ate))}</p>
      <div className="grid g4k">
        <Kpi lead label={tr("Recebido pelo site")} value={money(p.vendas.receita)} foot={comparado(p.vendas.receita, p.vendas.receita_ant, p.periodo.dias)} />
        <Kpi label={tr("Pedidos pagos")} value={p.vendas.pedidos_pagos} foot={comparado(p.vendas.pedidos_pagos, p.vendas.pedidos_pagos_ant, p.periodo.dias)} />
        <Kpi label={tr("Conversão do pagamento")} value={foram ? `${(Math.round(1000 * pagaram / foram) / 10).toLocaleString(LOCALE())}%` : tr("sem dado")}
          foot={tr("{0} pagos de {1} que foram ao Stripe", pagaram, foram)} />
        <Kpi label={tr("Visitas")} value={p.visitas.total} foot={!p.visitas.desde ? tr("começa a contar com esta versão")
          : p.visitas.parcial ? tr("contando desde {0}", fmtDate(p.visitas.desde)) : comparado(p.visitas.total, p.visitas.total_ant, p.periodo.dias)} />
      </div>
      <Strip items={[
        { label: tr("Pagos sem vaga ({0} dias)", p.atencao.janela_dias), value: p.atencao.pedidos_sem_vaga, tone: p.atencao.pedidos_sem_vaga ? 'crit' : undefined },
        { label: tr("Avisos por e-mail que não saíram ({0} dias)", p.atencao.janela_dias), value: p.atencao.avisos_falharam, tone: p.atencao.avisos_falharam ? 'warn' : undefined },
        { label: tr("Agendamentos esperando"), value: p.atencao.agendamentos_pendentes, tone: p.atencao.agendamentos_pendentes ? 'warn' : undefined },
        { label: tr("Contas sem card ligado"), value: p.atencao.contas_sem_vinculo, tone: p.atencao.contas_sem_vinculo ? 'warn' : undefined },
      ]} />
      <div className="row wrap" style={{ gap: 8 }}>
        <Link className="btn sm ghost" to="/site/pedidos">{tr("Ver os pedidos")}</Link>
        <Link className="btn sm ghost" to="/site/agendamentos">{tr("Ver os agendamentos")}</Link>
        <Link className="btn sm ghost" to="/site/contas">{tr("Ligar as contas")}</Link>
      </div>

      <div className="grid g2">
        <Section title={tr("Recebido por dia")}>
          <Barras dias={p.dias} campo="receita" rotulo={tr("Recebido")} valor={v => money(v)} />
          <p className="small muted" style={{ margin: '8px 0 0' }}>{tr("Loja e carrinho {0} (depósitos dentro: {1}; ticket médio {2}) · planos {3} · sessões pagas pela invoice {4}",
            money(p.vendas.loja_e_carrinho), money(p.vendas.deposito), p.vendas.ticket_medio === null ? '—' : money(p.vendas.ticket_medio),
            money(p.vendas.planos), money(p.vendas.sessoes_invoice))}</p>
        </Section>
        <Section title={tr("Visitas por dia")}>
          {p.visitas.desde ? <>
            <Barras dias={p.dias} campo="visitas" rotulo={tr("Visitas")} valor={v => n(v)} />
            <p className="small muted" style={{ margin: '8px 0 0' }}>{tr("Contando desde {0}. Uma visita é uma página do site que chegou ao servidor (robôs não contam). Quem volta a uma página em menos de 5 minutos vê a que o navegador guardou, e essa não conta.", fmtDate(p.visitas.desde))}</p>
          </> : <Empty title={tr("Ainda sem visitas contadas")}>{tr("O painel conta as páginas abertas a partir desta versão, sem IP nem cookie. Os números aparecem aqui conforme as pessoas visitam o site.")}</Empty>}
        </Section>
      </div>

      <Section title={tr("Do carrinho ao pagamento")}>
        <ol className="sp-funil">{p.pagamento.funil.map((f, i) => {
          const base = Math.max(...p.pagamento.funil.map(x => x.n), 1)
          const ant = i ? p.pagamento.funil[i - 1].n : 0
          return <li key={f.etapa}>
            <span className="sp-funil-nome">{ETAPA[f.etapa]}</span>
            <span className="sp-rank-barra" aria-hidden="true"><i style={{ transform: `scaleX(${Math.min(1, f.n / base)})` }} /></span>
            <b className="mono">{n(f.n)}</b>
            <span className="small muted mono">{i && ant && f.n <= ant ? `${Math.round(100 * f.n / ant)}%` : ''}</span>
          </li>
        })}</ol>
        <p className="small muted" style={{ margin: '8px 0 0' }}>{tr("Do carrinho, no período: {0} esperando o banco, {1} não passaram, {2} expiraram sem pagar e {3} ainda no Stripe. \"Abriram o carrinho\" conta cada vez que a página abre.",
          p.pagamento.carrinho.aguardando, p.pagamento.carrinho.falhou, p.pagamento.carrinho.expirado, p.pagamento.carrinho.aberto)}</p>
        <p className="small muted" style={{ margin: '4px 0 0' }}>{tr("Buy now da loja (direto do produto ao Stripe): {0} foram ao pagamento e {1} pagaram.",
          p.pagamento.buy_now.foram, p.pagamento.buy_now.pago)}</p>
      </Section>

      <div className="grid g2">
        <Section title={tr("Produtos mais vendidos")} right={<span className="small muted">{tr("valor do item, sem depósito e frete")}</span>}>
          <Ranking vazio={tr("Nenhum produto vendido no período.")} itens={p.produtos.map(x => ({ rotulo: x.nome, n: x.qtd, extra: money(x.receita) }))} />
        </Section>
        <Section title={tr("Sessões vendidas no carrinho")}>
          <Ranking vazio={tr("Nenhuma sessão paga no carrinho no período.")} itens={p.servicos.map(x => ({ rotulo: x.nome, n: x.qtd, extra: money(x.receita) }))} />
          <p className="small muted" style={{ margin: '8px 0 0' }}>{tr("Agendamentos do site e da área do cliente no período: {0} marcados ({1} pelo site, {2} pela área), {3} cancelados ou recusados; {4} por vir.",
            p.sessoes.marcadas, p.sessoes.pelo_site, p.sessoes.pela_area, p.sessoes.canceladas, p.sessoes.proximas)}</p>
        </Section>
      </div>

      <div className="grid g2">
        <Section title={tr("Páginas mais vistas")}>
          <Ranking vazio={tr("Sem visitas contadas no período.")} itens={p.visitas.paginas.map(x => ({ rotulo: x.caminho, n: x.n }))} />
        </Section>
        <Section title={tr("De onde as pessoas entraram")}>
          <Ranking vazio={tr("Sem entradas contadas no período.")} itens={p.visitas.fontes.map(x => ({ rotulo: FONTE[x.fonte] || x.fonte, n: x.n }))} />
          {p.visitas.entradas > 0 && <p className="small muted" style={{ margin: '8px 0 0' }}>{tr("{0} entradas no site; navegar de uma página para outra não conta como entrada.", n(p.visitas.entradas))}</p>}
        </Section>
      </div>

      <div className="grid g2">
        <Section title={tr("Campanhas das vendas e dos contatos")}>
          <Ranking vazio={tr("Nenhuma venda ou contato com campanha (utm) no período.")} itens={p.campanhas.com_campanha.map(x => ({ rotulo: x.fonte, n: x.n }))} />
          <p className="small muted" style={{ margin: '8px 0 0' }}>{tr("{0} sem campanha marcada. Vem do utm que o agendamento, o plano ou o contato do site guardou.", p.campanhas.sem_campanha)}</p>
        </Section>
        <Section title={tr("Contas e contatos")}>
          <Strip items={[
            { label: tr("Contas novas no site"), value: p.contas.novas },
            { label: tr("Contatos e pedidos do site em Vendas"), value: p.leads.novos },
            { label: tr("Viraram venda (ganho)"), value: p.leads.ganhos, tone: p.leads.ganhos ? 'ok' : undefined },
            { label: tr("Perdidos"), value: p.leads.perdidos },
          ]} />
          <p className="small muted" style={{ margin: '8px 0 0' }}>{tr("Planos mensais pagos no período: {0}.", p.vendas.planos_pagos)}</p>
        </Section>
      </div>

      <Section title={tr("Saúde do site")}>
        <Strip items={[
          { label: tr("Páginas servidas"), value: p.saude.paginas.n },
          { label: tr("Erros do servidor nas páginas"), value: p.saude.paginas.erros_5xx, tone: p.saude.paginas.erros_5xx ? 'crit' : 'ok' },
          { label: tr("Página mais lenta (p95)"), value: p.saude.paginas.p95_ms === null ? '—' : `${Math.round(p.saude.paginas.p95_ms)} ms` },
          { label: tr("Erros no carrinho e no pagamento"), value: p.saude.compra.erros_5xx, tone: p.saude.compra.erros_5xx ? 'crit' : 'ok' },
        ]} />
        <p className="small muted" style={{ margin: '8px 0 0' }}>{tr("Desde o último reinício do servidor ({0}).", fmtDateTime(p.saude.desde))}</p>
      </Section>
    </>}
  </div>
}
