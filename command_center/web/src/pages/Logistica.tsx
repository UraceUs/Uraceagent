/* Planejamento — a seção de Logística que ainda não existe (Pedidos e Compras nasceram em
 * 30/09, em Compras.tsx).
 *
 * Elas estão no menu porque o dono pediu a seção inteira (23/09). Cada uma diz o que
 * vai ser e o que falta para nascer. **Nenhuma inventa número**: tela que mostra dado
 * de mentira para parecer pronta é pior que tela vazia — a pessoa decide em cima dela.
 */
import { Link } from 'react-router-dom'
import { useGet } from '../api/hooks'
import { Banner, Kpi, PageHeader, Section } from '../components/ui'
import { tr } from '../i18n'

interface Lista { itens: { id: number; name: string; unit: string; nosso: number; min_qty: number | null }[] }

export function Planejamento() {
  const lista = useGet<Lista>('/estoque')
  const itens = lista.data?.itens || []
  const semContagem = itens.filter(i => i.nosso === 0).length
  return <>
    <PageHeader title={tr("Planejamento")} help={tr("Peças e corridas: o que vai faltar, e quando.")} />
    <Banner tone="info">{tr("Os gráficos ainda não foram construídos. O consumo por mês existe — saiu das 348 invoices do ano — mas ele está no arquivo que gerou o estoque, não numa tela. Enquanto isso, o que é verdade hoje está abaixo.")}</Banner>

    <div className="kpis">
      <Kpi label={tr("Itens no estoque")} value={itens.length} lead />
      <Kpi label={tr("Ainda sem contagem")} value={semContagem}
           tone={semContagem ? 'warn' : undefined}
           foot={semContagem ? tr("saldo zero: ninguém contou ainda") : tr("tudo contado")} />
    </div>

    <Section title={tr("O que vai ter aqui")}>
      <ul className="lst">
        <li><b>{tr("Peças:")}</b> {tr("consumo por mês de cada item, contra o que tem hoje — quantas semanas de estoque restam")}</li>
        <li><b>{tr("Corridas:")}</b> {tr("o que cada corrida do calendário costuma consumir, para comprar antes e não no dia")}</li>
        <li>{tr("Peça que está acabando mais rápido que o normal")}</li>
        <li>{tr("Dinheiro parado em prateleira, por tipo")}</li>
      </ul>
    </Section>

    <Section title={tr("O que falta para isso valer")}>
      <ul className="lst">
        <li><b>{tr("A contagem física.")}</b> {tr("Sem saber quanto tem hoje, nenhuma previsão vale.")}
          <Link to="/estoque"> {tr("Contar o estoque")}</Link></li>
        <li>{tr("Histórico de consumo dentro do painel (hoje ele vive no QuickBooks)")}</li>
        <li>{tr("Ligar consumo a corrida, para saber o custo de peça por evento")}</li>
      </ul>
    </Section>
  </>
}
