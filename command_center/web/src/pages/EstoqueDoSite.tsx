/* #309 · Site › Estoque do site. Dono, 16/10: "coloca o estoque do site, o que que a gente tem, aí a gente seleciona, não
 * precisa ficar aparente essa parte … para os clientes, mas a gente seleciona o que que é dropshipping e o que que a gente
 * tem em estoque para poder enviar. Um marcador para isso lá, e o que tiver em estoque a gente coloca quanto que tem".
 *
 * Cada produto da loja num cartão do padrão D: o marcador em cima (interno: o cliente nunca vê), o produto, quanto tem
 * agora (Galpão + Pista, o mesmo saldo do Balcão e da contagem) e a lista das opções, cada uma com o item do estoque
 * ligado. Ligar (a um item que já existe, ou criando o item a partir do produto) e Contar abrem num painel.
 *
 * Revisão do PR #320: a contagem é sempre de UM local, então a tela mostra cada local ("Galpão 5 · Pista 3") e o campo
 * "Quanto tem no Galpão agora" já vem com o saldo daquele local (mostrar só a soma fazia a pessoa digitar o total num
 * local e inflar o saldo). O item que já tem saldo liga sem contar. O cartão dropshipping que ainda tem ligação mostra a
 * ligação e o Desligar (senão o item ficava preso). `/site/estoque/<endereço>` abre já filtrado no produto. */
import { useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError, qs } from '../api/client'
import { useGet } from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import { Empty, ErrorState, Loading, Scrim, Section } from '../components/ui'
import { usePerguntar } from '../components/Perguntar'
import { Cartao } from '../components/Cartao'
import { useToast } from '../components/Toast'
import { fmtDateTime } from '../components/fmt'
import { tr } from '../i18n'

type Modo = 'todos' | 'estoque' | 'dropshipping' | 'sem_item' | 'sem_saldo'
type PorLocal = Record<string, number>
type Ligacao = { variation: string; item_id: number; item: string; kind: string; tracking: 'quantidade' | 'serie'; unit: string
  tem: number; por_local: PorLocal; ativo: boolean; preco_balcao: number | null; contado_em: string | null }
type Opcao = { variation: string; ligado: Ligacao | null; manual: boolean; no_site: boolean }
type ProdutoEstoque = { id: number; slug: string; name: string; active: boolean; fulfillment: 'dropshipping' | 'estoque'; foto: string | null
  price: number; price_min: number | null; price_max: number | null; no_site: boolean; opcoes: Opcao[]; orfas: Ligacao[]
  tem: number | null; faltam_ligar: number; sem_saldo: number; prateleira: string }
type Local = { code: string; name: string }
type Prateleira = { code: string; nome: string }
type Lista = { produtos: ProdutoEstoque[]; total: number; limit: number; offset: number; contagem: Record<Modo, number>
  locais: Local[]; prateleiras: Prateleira[] }
type ItemEstoque = { id: number; name: string; kind: string; tracking: 'quantidade' | 'serie'; unit: string; size: string | null
  category: string | null; price: number | null; sku: string | null; ligado_pid: number | null; ligado_var: string | null
  ligado_nome: string | null; ligado_fulfillment: 'dropshipping' | 'estoque' | null; tem: number; por_local: PorLocal; contado: boolean }
type Painel = { tipo: 'ligar' | 'contar'; p: ProdutoEstoque; o: Opcao | Ligacao }

const POR_PAGINA = 20
const POR_PAGINA_ITENS = 12            // a lista de itens do estoque no painel Ligar
const usd = (n: number) => n.toLocaleString('en-US', { style: 'currency', currency: 'USD' })
const qtd = (n: number) => n.toLocaleString('en-US', { maximumFractionDigits: 2 })
const fotoUrl = (src: string) => src.startsWith('/') ? src : `/_s/img/${src}`
const preco = (p: ProdutoEstoque) => p.price_min && p.price_max && p.price_max !== p.price_min ? `${usd(p.price_min)} – ${usd(p.price_max)}`
  : p.price ? usd(p.price) : tr("Sob consulta")
/** "Galpão", "Pista" (sem o "(OKC)"): o nome curto do local, para caber no celular. */
const curto = (nome: string) => nome.replace(/\s*\(.*\)\s*$/, '')
/** "Galpão 5 · Pista 3": cada local que conta para o site, com o que é da URACE ali. */
const porLocal = (locais: Local[], pl?: PorLocal) => locais.map(x => `${curto(x.name)} ${qtd(pl?.[x.code] ?? 0)}`).join(' · ')
/** "no Galpão" · "na Pista": o rótulo do campo da contagem diz de qual local é o número. */
const noLocal = (x?: Local) => !x ? '' : x.code === 'pista' ? tr("na {0}", curto(x.name)) : tr("no {0}", curto(x.name))
/** O número no campo (sem separador de milhar). */
const campo = (n: number | undefined) => String(Math.round((n ?? 0) * 100) / 100)
const MODOS: [Modo, string][] = [['todos', tr("Todos")], ['estoque', tr("Em estoque")], ['dropshipping', tr("Dropshipping")],
  ['sem_item', tr("Em estoque sem item ligado")], ['sem_saldo', tr("Sem saldo")]]

/** `produto`: o endereço do produto (`/site/estoque/<endereço>`, o link de Produtos da loja) abre a lista já filtrada
 * (quem chama põe `key`, para outro endereço recomeçar a busca). */
export function EstoqueDoSite({ produto }: { produto?: string }) {
  const { can } = useAuth()
  const gerente = can('MANAGER')
  const toast = useToast()
  const perguntar = usePerguntar()
  const [modo, setModo] = useState<Modo>('todos')
  const [texto, setTexto] = useState(produto ?? '')
  const [busca, setBusca] = useState(produto ?? '')
  const [offset, setOffset] = useState(0)
  const [painel, setPainel] = useState<Painel | null>(null)
  const [trocando, setTrocando] = useState(0)
  const l = useGet<Lista>(`/site/estoque${qs({ modo, q: busca, limit: POR_PAGINA, offset })}`)
  const recarregar = l.reload
  // o último cartão da página filtrada pode ter saído do filtro (ligou, mudou o marcador): só quando a página
  // recarregada vem VAZIA, volta para a última página que ainda tem cartão
  useEffect(() => {
    const d = l.data
    if (d && d.offset === offset && offset > 0 && !d.produtos.length) setOffset(Math.max(0, Math.floor((d.total - 1) / POR_PAGINA) * POR_PAGINA))
  }, [l.data, offset])

  async function trocar(p: ProdutoEstoque) {
    const novo = p.fulfillment === 'estoque' ? 'dropshipping' : 'estoque'
    // muda o que o site vende: confirma antes, dizendo o que muda
    if (!await perguntar(novo === 'dropshipping'
      ? { titulo: tr("Passar {0} a dropshipping?", p.name), texto: tr("O site passa a seguir a caixa \"Em estoque\" do produto e a venda paga deixa de sair do estoque do box. As ligações ficam no cartão até você desligar."), ok: tr("Passar a dropshipping") }
      : { titulo: tr("Passar {0} a em estoque?", p.name), texto: tr("Com item ligado, o site vende só o que o box tem (Galpão + Pista) e a venda paga sai do estoque. Até ligar, o site continua seguindo a caixa \"Em estoque\"."), ok: tr("Passar a em estoque") })) return
    setTrocando(p.id)
    try {
      await api.patch(`/site/produtos/${p.id}`, { fulfillment: novo })
      toast(novo === 'estoque' ? tr("Marcado como em estoque. Ligue cada opção a um item do estoque e conte o que tem.")
        : tr("Marcado como dropshipping: o site volta a seguir a caixa Em estoque do produto."), 'ok')
      recarregar()
    } catch (e) { toast((e as ApiError).message, 'crit') } finally { setTrocando(0) }
  }

  return <div className="stack" style={{ gap: 18 }}>
    <p className="small muted" style={{ margin: 0 }}>{tr("Interno: o cliente não vê o marcador nem a quantidade, só \"Out of stock\" quando acaba. Em estoque, quem diz se tem é o estoque do box (Galpão + Pista; o trailer de corrida fica fora), o mesmo saldo do Balcão, da contagem e de Compras: a venda paga no site sai dele sozinha. Dropshipping: o fornecedor envia, e o site segue a caixa \"Em estoque\" do produto.")}</p>
    <Section title={tr("Produtos da loja")} count={l.data?.total}>
      <div className="stack" style={{ gap: 12 }}>
        <div className="seg es-filtros" role="group" aria-label={tr("Quais produtos")}>
          {MODOS.map(([k, r]) => <button key={k} type="button" className={`btn sm${modo === k ? '' : ' ghost'}`} aria-pressed={modo === k}
            onClick={() => { setModo(k); setOffset(0) }}>{r}{l.data ? ` · ${l.data.contagem[k]}` : ''}</button>)}
        </div>
        <form className="row wrap" style={{ gap: 8 }} role="search" onSubmit={e => { e.preventDefault(); setBusca(texto.trim()); setOffset(0) }}>
          <label className="fld grow" style={{ margin: 0 }}><span>{tr("Buscar produto")}</span>
            <input type="search" value={texto} onChange={e => setTexto(e.target.value)} placeholder={tr("nome, SKU ou endereço")} enterKeyHint="search" /></label>
          <button className="btn" style={{ alignSelf: 'flex-end' }}>{tr("Buscar")}</button>
        </form>
        {l.error && <ErrorState error={l.error} retry={l.reload} />}
        {l.loading && !l.data && <Loading />}
        {l.data && (!l.data.produtos.length
          ? <Empty title={tr("Nenhum produto aqui")}>{modo === 'sem_item' ? tr("Todo produto em estoque já tem o item ligado.") : tr("Mude a busca ou o filtro.")}</Empty>
          : <div className="cd-grade">{l.data.produtos.map(p => <CartaoProduto key={p.id} p={p} locais={l.data!.locais} gerente={gerente}
            trocando={trocando === p.id} onTrocar={() => trocar(p)} onPainel={(tipo, o) => setPainel({ tipo, p, o })} onMudou={recarregar} />)}</div>)}
        {l.data && l.data.total > POR_PAGINA && <div className="row" style={{ gap: 8 }}>
          <button className="btn sm ghost" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - POR_PAGINA))}>{tr("Anteriores")}</button>
          <span className="small muted grow" style={{ textAlign: 'center' }}>{offset + 1}–{Math.min(offset + POR_PAGINA, l.data.total)} {tr("de")} {l.data.total}</span>
          <button className="btn sm ghost" disabled={offset + POR_PAGINA >= l.data.total} onClick={() => setOffset(offset + POR_PAGINA)}>{tr("Próximas")}</button></div>}
      </div>
    </Section>
    {painel && l.data && (painel.tipo === 'ligar'
      ? <PainelLigar p={painel.p} o={painel.o as Opcao} locais={l.data.locais} prateleiras={l.data.prateleiras} onFechar={() => setPainel(null)}
        onFeito={() => { setPainel(null); recarregar() }} />
      : <PainelContar p={painel.p} l={(painel.o as Opcao).ligado ?? painel.o as Ligacao} locais={l.data.locais} gerente={gerente}
        onFechar={() => setPainel(null)} onFeito={() => { setPainel(null); recarregar() }} />)}
  </div>
}

/** Desligar a opção do item (o item fica no estoque, com o saldo e o histórico). Devolve se desligou. */
function useDesligar() {
  const toast = useToast()
  const perguntar = usePerguntar()
  return async (p: ProdutoEstoque, l: Ligacao) => {
    const alvo = `${p.name}${l.variation ? ` · ${l.variation}` : ''}`
    if (!await perguntar({ titulo: tr("Desligar {0} do item {1}?", alvo, l.item), texto: tr("O item continua no estoque, com o saldo e o histórico. A venda do site deixa de baixar dele e, até ligar de novo, o site segue a caixa Em estoque."), ok: tr("Desligar"), perigo: true })) return false
    try { await api.del(`/site/estoque/${p.id}/ligar${qs({ variacao: l.variation })}`); toast(tr("Desligado."), 'ok'); return true }
    catch (x) { toast((x as ApiError).message, 'crit'); return false }
  }
}

function CartaoProduto({ p, locais, gerente, trocando, onTrocar, onPainel, onMudou }: { p: ProdutoEstoque; locais: Local[]; gerente: boolean
  trocando: boolean; onTrocar: () => void; onPainel: (tipo: 'ligar' | 'contar', o: Opcao | Ligacao) => void; onMudou: () => void }) {
  const em = p.fulfillment === 'estoque'
  const desligar = useDesligar()
  const [desligando, setDesligando] = useState('')
  const site = !p.active ? tr("escondido da loja") : p.no_site ? tr("no site: à venda") : tr("no site: Out of stock")
  // dropshipping que ainda tem ligação: mostra a ligação e o Desligar (o item não liga a outro produto até desligar)
  const linhas = em ? p.opcoes : p.opcoes.filter(o => o.ligado)
  const nome = (o: { variation: string }) => `${p.name}${o.variation ? ` · ${o.variation}` : ''}`
  async function tirar(l: Ligacao) {
    setDesligando(l.variation || '-')
    try { if (await desligar(p, l)) onMudou() } finally { setDesligando('') }
  }
  return <Cartao id={`es-${p.id}`} estado={em ? tr("Em estoque") : tr("Dropshipping")} tom={em ? 'ok' : 'info'}
    avatar={p.foto ? <img src={fotoUrl(p.foto)} alt="" width={60} height={60} loading="lazy" /> : <span>URACE</span>}
    nome={<Link to={`/site/produtos/${p.id}`}>{p.name}</Link>} sub={[`${preco(p)} · ${site}`]}
    grande={em ? (p.tem === null ? '—' : qtd(p.tem)) : <span className="es-texto">{tr("Fornecedor")}</span>}
    detalhe={em ? (p.tem === null ? tr("falta ligar ao estoque") : tr("tem agora · Galpão + Pista")) : tr("o fornecedor envia; o site segue a caixa Em estoque")}
    acoes={gerente ? <>
      <button type="button" className="btn" disabled={trocando} onClick={onTrocar}>{em ? tr("Passar a dropshipping") : tr("Passar a em estoque")}</button>
      <Link className="btn" to={`/site/produtos/${p.id}`}>{tr("Abrir o produto")}</Link></> : null}>
    {!em && (linhas.length > 0 || p.orfas.length > 0) && <p className="small es-aviso">{tr("Ainda ligado ao estoque, mas a venda não baixa daqui (dropshipping). Desligue para ligar o item a outro produto.")}</p>}
    {(linhas.length > 0 || p.orfas.length > 0) && <ul className="cd-lista">
      {linhas.map(o => {
        const tom = !o.ligado ? 'warn' : o.ligado.tem >= 1 ? 'ok' : 'crit'
        return <li key={o.variation || '-'}>
          <i className={`cd-ic ${tom}`} aria-hidden="true">{!o.ligado ? '!' : o.ligado.tem >= 1 ? '✓' : '0'}</i>
          <span className="grow"><b>{o.variation || tr("O produto")}</b>
            <span className="muted"> · {o.ligado ? o.ligado.item + (o.ligado.ativo ? '' : tr(" (excluído do estoque)")) : tr("sem item ligado: o site segue a caixa Em estoque")}</span>
            {o.ligado && <span className="small muted es-locais">{porLocal(locais, o.ligado.por_local)}</span>}</span>
          {o.ligado && <span className="es-tem">{qtd(o.ligado.tem)} <small>{o.ligado.unit}</small></span>}
          {o.ligado ? (em ? <button type="button" className="btn sm" onClick={() => onPainel('contar', o)}
            aria-label={tr("Contar {0}", nome(o))}>{o.ligado.tracking === 'serie' ? tr("Unidades") : tr("Contar")}</button>
            : gerente && <button type="button" className="btn sm" disabled={!!desligando} onClick={() => tirar(o.ligado!)}
              aria-label={tr("Desligar {0}", nome(o))}>{tr("Desligar")}</button>)
            : gerente && <button type="button" className="btn sm" onClick={() => onPainel('ligar', o)}
              aria-label={tr("Ligar {0} ao estoque", nome(o))}>{tr("Ligar")}</button>}
        </li>
      })}
      {p.orfas.map(x => <li key={`orfa-${x.variation}`}>
        <i className="cd-ic warn" aria-hidden="true">?</i>
        <span className="grow"><b>{x.variation || tr("O produto")}</b><span className="muted"> · {tr("opção que não existe mais no produto: {0}", x.item)}</span></span>
        {gerente && <button type="button" className="btn sm ghost" onClick={() => onPainel('contar', x)}>{tr("Ver")}</button>}
      </li>)}
    </ul>}
  </Cartao>
}

function PainelLigar({ p, o, locais, prateleiras, onFechar, onFeito }: { p: ProdutoEstoque; o: Opcao; locais: Local[]; prateleiras: Prateleira[]
  onFechar: () => void; onFeito: () => void }) {
  const toast = useToast()
  const alvo = `${p.name}${o.variation ? ` · ${o.variation}` : ''}`
  const [jeito, setJeito] = useState<'existe' | 'criar'>('existe')
  const [texto, setTexto] = useState('')
  const [busca, setBusca] = useState('')
  const [item, setItem] = useState<ItemEstoque | null>(null)
  const [novo, setNovo] = useState({ name: alvo.replace(' · ', ' '), category: p.prateleira, size: o.variation, price: '' })
  const [contagem, setContagem] = useState('')
  const [mexeu, setMexeu] = useState(false)
  const [local, setLocal] = useState(locais[0]?.code || 'sede')
  const [indo, setIndo] = useState(false)
  const [pag, setPag] = useState(0)
  const r = useGet<{ itens: ItemEstoque[]; total: number; offset: number; sugestao: boolean }>(jeito === 'existe' ? `/site/estoque/itens${qs({ q: busca, produto: p.id, limit: POR_PAGINA_ITENS, offset: pag })}` : null)
  const serie = jeito === 'existe' && item?.tracking === 'serie'
  // o item que já tem saldo (ou contagem) liga sem contar: o campo vem com o saldo do local e só vai se a pessoa mudar
  const opcional = jeito === 'existe' && !!item?.contado
  const aqui = locais.find(x => x.code === local) || locais[0]
  const conta = serie || (opcional && (!mexeu || contagem.trim() === '')) ? null : contagem
  function preencher(i: ItemEstoque | null, code: string) { setContagem(i?.contado ? campo(i.por_local[code]) : ''); setMexeu(false) }
  // busca nova: começa da primeira página e solta o item escolhido (ele podia ser ligado sem estar na tela)
  function buscar() { setBusca(texto.trim()); setPag(0); setItem(null); preencher(null, local) }

  async function ligar(e: FormEvent) {
    e.preventDefault()
    if (jeito === 'existe' && !item) { toast(tr("Escolha o item do estoque."), 'warn'); return }
    if (!serie && !opcional && contagem.trim() === '') { toast(tr("Informe quanto tem agora: é o que o site passa a vender."), 'warn'); return }
    setIndo(true)
    try {
      await api.post(`/site/estoque/${p.id}/ligar`, { variacao: o.variation, local, contagem: conta,
        ...(jeito === 'existe' ? { item_id: item!.id } : { criar: { name: novo.name.trim() || null, category: novo.category || null, size: novo.size.trim() || null, price: novo.price.trim() || null } }) })
      toast(tr("Ligado: o site já vende pelo estoque."), 'ok'); onFeito()
    } catch (x) { toast((x as ApiError).message, 'crit'); setIndo(false) }
  }

  return <Scrim onMouseDown={onFechar}><form className="modal stack es-modal" role="dialog" aria-modal="true" aria-labelledby="es-ligar-h"
    style={{ maxWidth: 560, gap: 12 }} onMouseDown={e => e.stopPropagation()} onSubmit={ligar}>
    <h3 id="es-ligar-h">{tr("Ligar ao estoque: {0}", alvo)}</h3>
    <p className="small muted" style={{ margin: 0 }}>{tr("Um saldo só: o mesmo do Balcão, da contagem e de Compras. Conta o que é da URACE no Galpão e na Pista; peça de cliente nunca vai para o site.")}</p>
    <div className="seg" role="group" aria-label={tr("Qual item")}>
      <button type="button" className={`btn sm${jeito === 'existe' ? '' : ' ghost'}`} aria-pressed={jeito === 'existe'} onClick={() => { setJeito('existe'); preencher(item, local) }}>{tr("Item do estoque")}</button>
      <button type="button" className={`btn sm${jeito === 'criar' ? '' : ' ghost'}`} aria-pressed={jeito === 'criar'} onClick={() => { setJeito('criar'); preencher(null, local) }}>{tr("Criar item")}</button>
    </div>
    {jeito === 'existe' ? <>
      <div className="row wrap" style={{ gap: 8 }}>
        <label className="fld grow" style={{ margin: 0 }}><span>{tr("Buscar no estoque")}</span>
          <input type="search" value={texto} onChange={e => setTexto(e.target.value)} enterKeyHint="search"
            onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); buscar() } }} /></label>
        <button type="button" className="btn" style={{ alignSelf: 'flex-end' }} onClick={buscar}>{tr("Buscar")}</button>
      </div>
      {r.error && <ErrorState error={r.error} retry={r.reload} />}
      {r.loading && !r.data && <Loading rows={2} />}
      {r.data && <>
        {r.data.sugestao && !busca && <p className="small muted" style={{ margin: 0 }}>{tr("Sugestão pelo nome do produto:")}</p>}
        {!r.data.itens.length ? <p className="small muted" style={{ margin: 0 }}>{tr("Nenhum item com esse nome. Busque outro, ou crie o item a partir do produto.")}</p>
          : <ul className="es-itens" role="radiogroup" aria-label={tr("Itens do estoque")}>{r.data.itens.map(i => {
            const ocupado = !!i.ligado_pid && !(i.ligado_pid === p.id && (i.ligado_var || '') === o.variation)
            const onde = `${i.ligado_nome}${i.ligado_var ? ` · ${i.ligado_var}` : ''}`
            return <li key={i.id}><label className={`es-item${item?.id === i.id ? ' on' : ''}${ocupado ? ' off' : ''}`}>
              <input type="radio" name="es-item" checked={item?.id === i.id} disabled={ocupado} onChange={() => { setItem(i); preencher(i, local) }} />
              <span className="grow"><b>{i.name}</b>{i.size ? <span className="muted"> · {i.size}</span> : null}
                <span className="small muted es-item-sub">{ocupado ? (i.ligado_fulfillment === 'dropshipping' ? tr("ligado a {0} (dropshipping)", onde) : tr("já vende no site como {0}", onde))
                  : i.tracking === 'serie' ? tr("número de série, disponíveis: {0}", porLocal(locais, i.por_local)) : tr("tem {0} ({1})", porLocal(locais, i.por_local), i.unit)}</span></span>
            </label></li>
          })}</ul>}
        {r.data.total > r.data.itens.length + pag || pag > 0 ? <div className="row" style={{ gap: 8 }}>
          <button type="button" className="btn sm ghost" disabled={pag === 0} onClick={() => setPag(Math.max(0, pag - POR_PAGINA_ITENS))}>{tr("Anteriores")}</button>
          <span className="small muted grow" style={{ textAlign: 'center' }}>{tr("{0}–{1} de {2} itens", pag + 1, pag + r.data.itens.length, r.data.total)}</span>
          <button type="button" className="btn sm ghost" disabled={pag + POR_PAGINA_ITENS >= r.data.total} onClick={() => setPag(pag + POR_PAGINA_ITENS)}>{tr("Próximas")}</button></div> : null}
      </>}
    </> : <div className="es-campos">
      <label className="fld" style={{ gridColumn: '1 / -1' }}><span>{tr("Nome do item no estoque")}</span>
        <input value={novo.name} maxLength={120} onChange={e => setNovo({ ...novo, name: e.target.value })} /></label>
      <label className="fld"><span>{tr("Prateleira")}</span><select value={novo.category} onChange={e => setNovo({ ...novo, category: e.target.value })}>
        {prateleiras.map(x => <option key={x.code} value={x.code}>{x.nome}</option>)}</select></label>
      <label className="fld"><span>{tr("Tamanho ou medida")} <i>{tr("opcional")}</i></span>
        <input value={novo.size} maxLength={60} onChange={e => setNovo({ ...novo, size: e.target.value })} /></label>
      <label className="fld" style={{ gridColumn: '1 / -1' }}><span>{tr("Preço no Balcão (US$)")} <i>{tr("opcional; o preço do site fica no produto")}</i></span>
        <input inputMode="decimal" value={novo.price} onChange={e => setNovo({ ...novo, price: e.target.value })} /></label>
    </div>}
    {serie ? <p className="small" style={{ margin: 0 }}>{tr("Item com número de série: o site vende as unidades disponíveis da URACE, uma a uma (a entrada de cada unidade é pelo Estoque).")}</p>
      : <div className="es-campos">
        <label className="fld"><span>{tr("Quanto tem {0} agora", noLocal(aqui))} <i>{opcional ? tr("opcional: mude só se contou") : tr("a contagem")}</i></span>
          <input inputMode="decimal" value={contagem} required={!opcional} onChange={e => { setContagem(e.target.value); setMexeu(true) }} placeholder="0" /></label>
        <label className="fld"><span>{tr("Onde")}</span><select value={local} onChange={e => { setLocal(e.target.value); if (!mexeu) preencher(jeito === 'existe' ? item : null, e.target.value) }}>
          {locais.map(x => <option key={x.code} value={x.code}>{x.name}</option>)}</select></label>
        <span className="small muted" style={{ gridColumn: '1 / -1' }}>{jeito === 'existe' && item ? tr("Agora: {0}.", porLocal(locais, item.por_local)) + ' ' : ''}{tr("A contagem vira o saldo do local escolhido; os outros ficam como estão.")}</span>
      </div>}
    <div className="modal-foot">
      <button type="button" className="btn ghost" onClick={onFechar}>{tr("Cancelar")}</button>
      <button className="btn primary" disabled={indo}>{indo ? tr("Ligando…") : conta === null ? tr("Ligar") : tr("Ligar e contar")}</button>
    </div>
  </form></Scrim>
}

function PainelContar({ p, l, locais, gerente, onFechar, onFeito }: { p: ProdutoEstoque; l: Ligacao; locais: Local[]; gerente: boolean
  onFechar: () => void; onFeito: () => void }) {
  const toast = useToast()
  const tirar = useDesligar()
  const alvo = `${p.name}${l.variation ? ` · ${l.variation}` : ''}`
  const [local, setLocal] = useState(locais[0]?.code || 'sede')
  // o campo vem com o saldo do local escolhido: a contagem redefine aquele local, nunca a soma
  const [contagem, setContagem] = useState(campo(l.por_local?.[locais[0]?.code || 'sede']))
  const [indo, setIndo] = useState(false)
  const aqui = locais.find(x => x.code === local) || locais[0]
  const orfa = !p.opcoes.some(o => o.variation === l.variation)
  const serie = l.tracking === 'serie'

  async function contar(e: FormEvent) {
    e.preventDefault()
    if (contagem.trim() === '') { toast(tr("Informe quanto a mão contou."), 'warn'); return }
    setIndo(true)
    try {
      const r = await api.post<{ antes: number; depois: number }>(`/site/estoque/${p.id}/contar`, { variacao: l.variation, qty: contagem, local })
      toast(tr("Contado: {0} → {1}.", qtd(r.antes), qtd(r.depois)), 'ok'); onFeito()
    } catch (x) { toast((x as ApiError).message, 'crit'); setIndo(false) }
  }
  async function desligar() {
    setIndo(true)
    if (await tirar(p, l)) onFeito(); else setIndo(false)
  }

  return <Scrim onMouseDown={onFechar}><form className="modal stack es-modal" role="dialog" aria-modal="true" aria-labelledby="es-contar-h"
    style={{ maxWidth: 480, gap: 12 }} onMouseDown={e => e.stopPropagation()} onSubmit={contar}>
    <h3 id="es-contar-h">{serie || orfa ? alvo : tr("Contar: {0}", alvo)}</h3>
    <p style={{ margin: 0 }}><b>{l.item}</b><br /><span className="small muted">{tr("tem {0} {1}: {2}", qtd(l.tem), l.unit, porLocal(locais, l.por_local))}
      {l.contado_em ? tr(" · contado em {0}", fmtDateTime(l.contado_em)) : ''}{l.preco_balcao !== null ? tr(" · Balcão {0}", usd(l.preco_balcao)) : ''}</span></p>
    {orfa ? <p className="small" style={{ margin: 0 }}>{tr("Esta opção não existe mais no produto (mudou de nome ou saiu). Desligue e ligue o item na opção certa.")}</p>
      : serie ? <p className="small" style={{ margin: 0 }}>{tr("Item com número de série: a contagem é conferir as unidades uma a uma, em Estoque.")} <Link to="/estoque">{tr("Abrir o Estoque")}</Link></p>
        : <div className="es-campos">
          <label className="fld"><span>{tr("Quanto tem {0} agora", noLocal(aqui))}</span>
            <input inputMode="decimal" value={contagem} required onChange={e => setContagem(e.target.value)} placeholder="0" /></label>
          <label className="fld"><span>{tr("Onde")}</span><select value={local} onChange={e => { setLocal(e.target.value); setContagem(campo(l.por_local?.[e.target.value])) }}>
            {locais.map(x => <option key={x.code} value={x.code}>{x.name}</option>)}</select></label>
          <span className="small muted" style={{ gridColumn: '1 / -1' }}>{tr("A contagem vira o saldo daquele local, e a diferença fica no histórico do item (a mesma de Estoque › Quantidade).")}</span>
        </div>}
    <div className="modal-foot">
      {gerente && <button type="button" className="btn ghost" disabled={indo} onClick={desligar}>{tr("Desligar do produto")}</button>}
      <button type="button" className="btn ghost" onClick={onFechar}>{tr("Fechar")}</button>
      {!serie && !orfa && <button className="btn primary" disabled={indo}>{indo ? tr("Salvando…") : tr("Salvar a contagem")}</button>}
    </div>
  </form></Scrim>
}
