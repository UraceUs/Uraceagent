/* Pedidos, Compras e Planejamento — as três seções de Logística que ainda não existem.
 *
 * Elas estão no menu porque o dono pediu a seção inteira (23/09). Cada uma diz o que
 * vai ser e o que falta para nascer. **Nenhuma inventa número**: tela que mostra dado
 * de mentira para parecer pronta é pior que tela vazia — a pessoa decide em cima dela.
 */
import { Link } from 'react-router-dom'
import { useGet } from '../api/hooks'
import { Banner, Empty, Kpi, PageHeader, Section } from '../components/ui'

interface Repor { id: number; name: string; unit: string; falta: number; sku: string | null; supplier_url: string | null }
interface Lista { itens: { id: number; name: string; unit: string; nosso: number; min_qty: number | null }[]; repor: Repor[] }

function EmConstrucao({ titulo, oque, falta, depende }: {
  titulo: string; oque: string; falta: string[]; depende?: { texto: string; para: string }
}) {
  return <>
    <PageHeader title={titulo} />
    <Banner tone="info">Esta parte ainda não foi construída. O que está escrito aqui é o
      combinado — não há número de mentira nesta tela.</Banner>
    <Section title="Para que serve">
      <p>{oque}</p>
    </Section>
    <Section title="O que falta" count={falta.length}>
      <ul className="lst">{falta.map(f => <li key={f}>{f}</li>)}</ul>
    </Section>
    {depende && <Section title="Depende de">
      <p>{depende.texto} <Link to={depende.para}>Ver</Link></p>
    </Section>}
  </>
}

export function Pedidos() {
  return <EmConstrucao
    titulo="Pedidos"
    oque="Pedido interno: o mecânico precisa de uma peça, pede pelo painel, e a pessoa que
          compra vê a fila num lugar só. Hoje isso acontece por mensagem e se perde."
    falta={[
      'Quem pede, o que pede, para qual kart ou corrida, e para quando',
      'Fila com estado: pedido → comprado → chegou → entregue',
      'Pedido que vira compra sem alguém redigitar',
      'Aviso quando o que chegou não é o que foi pedido',
    ]} />
}

export function Compras() {
  const lista = useGet<Lista>('/estoque')
  const repor = lista.data?.repor || []
  return <>
    <PageHeader title="Compras" help="O que falta comprar, pelo estoque mínimo." />
    <Banner tone="info">O módulo de compras ainda não existe — não há pedido de compra,
      nem cotação, nem recebimento. O que já funciona é a <b>lista do que falta</b>, que
      sai do estoque mínimo e traz o SKU da Comet para você pedir.</Banner>

    <div className="kpis">
      <Kpi label="Itens abaixo do mínimo" value={repor.length} tone={repor.length ? 'warn' : undefined} lead />
      <Kpi label="Com SKU do fornecedor" value={repor.filter(r => r.sku).length}
           foot="dá para pedir direto" />
    </div>

    <Section title="Lista de reposição" count={repor.length}>
      {!repor.length
        ? <Empty title="Nada faltando">Ou o estoque está em ordem, ou ninguém contou ainda.
          A contagem é que diz quanto tem. <Link to="/estoque">Ver o estoque</Link></Empty>
        : <div className="tbl">
          {repor.map(r => <div className="tr" key={r.id}>
            <div className="grow"><b>{r.name}</b>
              {r.sku ? <span className="small muted"> · SKU {r.sku}</span>
                : <span className="small muted"> · sem SKU: não dá para pedir automático</span>}</div>
            <span className="small">faltam <b>{r.falta}</b> {r.unit}</span>
            {r.supplier_url && <a className="btn ghost sm" href={r.supplier_url} target="_blank" rel="noreferrer">abrir</a>}
          </div>)}
        </div>}
    </Section>

    <Section title="O que falta construir">
      <ul className="lst">
        <li>Pedido de compra de verdade: o que foi pedido, quando, por quanto</li>
        <li>Recebimento que dá entrada no estoque sozinho</li>
        <li>Preço de revenda da Comet (o catálogo público mostra o preço de tabela)</li>
        <li>Ligar cada item ao SKU do fornecedor — hoje só alguns têm</li>
      </ul>
    </Section>
  </>
}

export function Planejamento() {
  const lista = useGet<Lista>('/estoque')
  const itens = lista.data?.itens || []
  const semContagem = itens.filter(i => i.nosso === 0).length
  return <>
    <PageHeader title="Planejamento" help="Peças e corridas: o que vai faltar, e quando." />
    <Banner tone="info">Os gráficos ainda não foram construídos. O consumo por mês existe
      — saiu das 348 invoices do ano — mas ele está no arquivo que gerou o estoque, não
      numa tela. Enquanto isso, o que é verdade hoje está abaixo.</Banner>

    <div className="kpis">
      <Kpi label="Itens no estoque" value={itens.length} lead />
      <Kpi label="Ainda sem contagem" value={semContagem}
           tone={semContagem ? 'warn' : undefined}
           foot={semContagem ? 'saldo zero: ninguém contou ainda' : 'tudo contado'} />
    </div>

    <Section title="O que vai ter aqui">
      <ul className="lst">
        <li><b>Peças:</b> consumo por mês de cada item, contra o que tem hoje — quantas
          semanas de estoque restam</li>
        <li><b>Corridas:</b> o que cada corrida do calendário costuma consumir, para
          comprar antes e não no dia</li>
        <li>Peça que está acabando mais rápido que o normal</li>
        <li>Dinheiro parado em prateleira, por tipo</li>
      </ul>
    </Section>

    <Section title="O que falta para isso valer">
      <ul className="lst">
        <li><b>A contagem física.</b> Sem saber quanto tem hoje, nenhuma previsão vale.
          <Link to="/estoque"> Contar o estoque</Link></li>
        <li>Histórico de consumo dentro do painel (hoje ele vive no QuickBooks)</li>
        <li>Ligar consumo a corrida, para saber o custo de peça por evento</li>
      </ul>
    </Section>
  </>
}
