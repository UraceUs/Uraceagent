/* Produtos da loja (#298). Dono, 16/10: "nos produtos da loja, colocar o valor de envio, o shipping … o valor do
 * Security Deposit … que eu consiga alterar … essas funções serão necessárias que sejam ativas permanentemente".
 * Decisões: frete = valor fixo por produto; no painel = tudo do produto. A lista é paginada no servidor; o produto
 * abre no próprio endereço (/site/produtos/12). Esconder não apaga: o produto sai da loja e continua aqui.
 * #309: "Como vendemos" (dropshipping ou em estoque) é interno; em estoque com item ligado, quem diz se tem é o
 * estoque do box (a caixa "Em estoque" vira só leitura e mostra quanto tem), e a ligação mora em Estoque do site.
 * Revisão: cada opção vai com o nome de antes (`antes`), para a ligação com o estoque seguir a opção renomeada; os
 * links para o Estoque do site abrem já filtrados no produto (`/site/estoque/<endereço>`). */
import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { useGet } from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import { Chip, Empty, ErrorState, Loading, Section } from '../components/ui'
import { EditorTexto } from '../components/EditorTexto'
import { InserirNoTopo } from '../components/Inserir'
import { Cartao, CdItem, CdLista } from '../components/Cartao'
import { useToast } from '../components/Toast'
import { fmtDateTime } from '../components/fmt'
import { tr } from '../i18n'

interface Foto { src: string; alt: string }
interface Variacao { id?: number | null; attrs: string[]; price: number; regular: number; in_stock: boolean }
interface Categoria { slug: string; name: string }
type Fulfillment = 'dropshipping' | 'estoque'
interface Ligacao { variation: string; item_id: number; item: string; tracking: 'quantidade' | 'serie'; unit: string; tem: number }
interface Produto { id: number; slug: string; name: string; type: 'simple' | 'variable'; price: number; regular: number; on_sale: boolean
  price_min: number | null; price_max: number | null; short: string; description: string; images: Foto[]; categories: Categoria[]
  attributes: { name: string; terms: string[] }[]; variations: Variacao[]; in_stock: boolean; sku: string
  shipping_fee: number | null; deposit: number; active: boolean; sort: number; origin: string | null; updated_at: string | null
  categorias_loja?: string[]; fulfillment: Fulfillment
  estoque?: { ligados: Record<string, Ligacao>; no_site: boolean; tem: number | null } }
interface Lista { produtos: Produto[]; total: number; limit: number; offset: number; categorias: Categoria[] }

const POR_PAGINA = 30
const usd = (n: number) => n.toLocaleString('en-US', { style: 'currency', currency: 'USD' })
/** A foto no painel: as do site moram em /_s/img; as subidas aqui já vêm com o caminho (/store/img/…). */
const fotoUrl = (src: string) => src.startsWith('/') ? src : `/_s/img/${src}`
const preco = (p: Produto) => p.price_min && p.price_max && p.price_max !== p.price_min ? `${usd(p.price_min)} – ${usd(p.price_max)}`
  : p.price ? usd(p.price) : tr("Sob consulta")
const frete = (v: number | null) => v === null ? tr("frete a combinar") : v === 0 ? tr("frete grátis") : tr("frete {0}", usd(v))
const qtd = (n: number) => n.toLocaleString('en-US', { maximumFractionDigits: 2 })

export function ProdutosDaLoja() {
  const { can } = useAuth()
  const nav = useNavigate()
  const toast = useToast()
  const [q, setQ] = useState('')
  const [busca, setBusca] = useState('')
  const [categoria, setCategoria] = useState('')
  const [estado, setEstado] = useState('')
  const [offset, setOffset] = useState(0)
  const [novo, setNovo] = useState({ name: '', regular: '', categories: ['parts'] })
  useEffect(() => { const t = setTimeout(() => { setBusca(q); setOffset(0) }, 300); return () => clearTimeout(t) }, [q])
  const qs = new URLSearchParams({ limit: String(POR_PAGINA), offset: String(offset), ...(busca ? { q: busca } : {}),
    ...(categoria ? { categoria } : {}), ...(estado ? { estado } : {}) })
  const l = useGet<Lista>(`/site/produtos?${qs}`)
  async function criar() {
    try {
      const r = await api.post<{ id: number }>('/site/produtos', { ...novo, active: false })
      toast(tr("Produto criado, ainda escondido: complete e ponha à venda."), 'ok')
      nav(`/site/produtos/${r.id}`)
    } catch (er) { toast((er as ApiError).message, 'crit') }
  }
  return <div className="stack" style={{ gap: 14 }}>
    {/* #312: o "Novo produto" fica no topo (antes ficava depois dos 70 produtos e da paginação) */}
    {can('MANAGER') && <InserirNoTopo rotulo={tr("Novo produto")} primario>
      <div className="loja-grade">
        <label className="fld"><span>{tr("Nome")} <i>{tr("o cliente lê, em inglês")}</i></span><input value={novo.name} onChange={e => setNovo({ ...novo, name: e.target.value })} /></label>
        <label className="fld"><span>{tr("Preço (US$)")}</span><input inputMode="decimal" value={novo.regular} onChange={e => setNovo({ ...novo, regular: e.target.value })} /></label>
        <label className="fld"><span>{tr("Categoria")}</span><select value={novo.categories[0]} onChange={e => setNovo({ ...novo, categories: [e.target.value] })}>
          {(l.data?.categorias || []).map(c => <option key={c.slug} value={c.slug}>{c.name}</option>)}</select></label>
        <div><button className="btn primary" disabled={novo.name.trim().length < 2} onClick={criar}>{tr("Criar e abrir")}</button></div>
      </div>
    </InserirNoTopo>}
    <p className="small muted" style={{ margin: 0 }}>{tr("Os produtos da loja do site. Frete: valor fixo por unidade, cobrado no pagamento quando o cliente escolhe \"Ship to me\" (vazio: a equipe combina à parte; 0: grátis). Retirar na pista é sempre grátis.")}</p>
    <div className="loja-filtros">
      <label className="fld"><span>{tr("Buscar")}</span><input type="search" value={q} placeholder={tr("nome, SKU ou endereço")} onChange={e => setQ(e.target.value)} /></label>
      <label className="fld"><span>{tr("Categoria")}</span><select value={categoria} onChange={e => { setCategoria(e.target.value); setOffset(0) }}>
        <option value="">{tr("Todas")}</option>{(l.data?.categorias || []).map(c => <option key={c.slug} value={c.slug}>{c.name}</option>)}</select></label>
      <label className="fld"><span>{tr("Mostrar")}</span><select value={estado} onChange={e => { setEstado(e.target.value); setOffset(0) }}>
        <option value="">{tr("Todos")}</option><option value="ativos">{tr("À venda")}</option><option value="escondidos">{tr("Escondidos")}</option></select></label>
    </div>
    {l.error && <ErrorState error={l.error} retry={l.reload} />}
    {l.loading && !l.data && <Loading />}
    {l.data && (!l.data.produtos.length ? <Empty title={tr("Nenhum produto aqui")}>{tr("Mude a busca ou os filtros.")}</Empty>
      : <div className="cd-grade">{l.data.produtos.map(p => {
        const sem = !(p.estoque?.no_site ?? p.in_stock)
        return <Cartao key={p.id} id={`produto-${p.id}`} nivel={2} estado={!p.active ? tr("escondido") : sem ? tr("sem estoque") : tr("à venda")} tom={!p.active ? 'neutral' : sem ? 'warn' : 'ok'}
          avatar={p.images[0] ? <img src={fotoUrl(p.images[0].src)} alt="" width={60} height={60} loading="lazy" /> : <span>URACE</span>}
          nome={<Link to={`/site/produtos/${p.id}`}>{p.name}</Link>}
          sub={[`${frete(p.shipping_fee)}${p.deposit ? ` · ${tr("depósito {0}", usd(p.deposit))}` : ''}`]}
          grande={preco(p)} acoes={<Link className="btn" to={`/site/produtos/${p.id}`}>{tr("Editar")}</Link>}>
          {(p.fulfillment === 'estoque' || p.on_sale || (!p.active && sem)) && <CdLista>
            {!p.active && sem && <CdItem tom="warn">{tr("sem estoque")}</CdItem>}
            {p.fulfillment === 'estoque' && <CdItem tom="info" valor={tr("interno: o cliente não vê")}>{p.estoque?.tem != null
              ? tr("em estoque · {0}", qtd(p.estoque.tem)) : tr("em estoque · falta ligar")}</CdItem>}
            {p.on_sale && <CdItem tom="info" glifo="%">{tr("promoção")}</CdItem>}
          </CdLista>}
        </Cartao>
      })}</div>)}
    {l.data && l.data.total > POR_PAGINA && <div className="row" style={{ gap: 8 }}>
      <button className="btn sm ghost" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - POR_PAGINA))}>{tr("Anteriores")}</button>
      <span className="small muted grow" style={{ textAlign: 'center' }}>{offset + 1}–{Math.min(offset + POR_PAGINA, l.data.total)} {tr("de")} {l.data.total}</span>
      <button className="btn sm ghost" disabled={offset + POR_PAGINA >= l.data.total} onClick={() => setOffset(offset + POR_PAGINA)}>{tr("Próximas")}</button></div>}
  </div>
}

type Edicao = Partial<{ name: string; regular: string; promo: string; sku: string; in_stock: boolean; active: boolean; fulfillment: Fulfillment
  shipping_fee: string; deposit: string; categories: string[]; short: string; description: string; images: Foto[]
  attribute_names: string[]; variations: { attrs: string[]; regular: string; promo: string; in_stock: boolean; antes: string | null }[] }>

const txt = (n: number | null | undefined) => n === null || n === undefined ? '' : String(n)

export function EditarProduto({ id }: { id: number }) {
  const { can } = useAuth()
  const gerente = can('MANAGER')
  const toast = useToast()
  const l = useGet<{ produto: Produto; categorias: Categoria[] }>(`/site/produtos/${id}`)
  const [e, setE] = useState<Edicao>({})
  const [subindo, setSubindo] = useState(false)
  const [salvando, setSalvando] = useState(false)
  if (l.error && !l.data) return <ErrorState error={l.error} retry={l.reload} />
  if (!l.data) return <Loading />
  const p = l.data.produto
  const muda = (x: Edicao) => setE(y => ({ ...y, ...x }))
  const promoDe = (price: number, regular: number) => price < regular ? String(price) : ''
  const fotos = e.images ?? p.images
  const cats = e.categories ?? p.categorias_loja ?? p.categories.map(c => c.slug)
  const nomes = e.attribute_names ?? p.attributes.map(a => a.name)
  // `antes`: o nome da opção quando a tela abriu (null na opção nova): renomear a opção ligada leva a ligação junto
  const vars = e.variations ?? p.variations.map(v => ({ attrs: v.attrs, regular: txt(v.regular), promo: promoDe(v.price, v.regular), in_stock: v.in_stock, antes: v.attrs.join(' / ') }))
  const mudou = Object.keys(e).length > 0
  // #309: em estoque com item ligado, o "Em estoque" é do estoque (só leitura); sem item ligado, vale a caixa
  const emEstoque = (e.fulfillment ?? p.fulfillment) === 'estoque'
  const ligados = p.estoque?.ligados || {}
  const ligado = (nome: string) => emEstoque ? ligados[nome] : undefined
  async function salvar(extra?: Edicao) {
    setSalvando(true)
    try {
      const corpo: Record<string, unknown> = { ...e, ...extra }
      if ('promo' in corpo && corpo.promo === '') corpo.promo = null
      if ('variations' in corpo) corpo.variations = vars.map(v => ({ ...v, promo: v.promo === '' ? null : v.promo }))
      await api.patch(`/site/produtos/${id}`, corpo)
      toast(tr("Salvo: a loja do site já mostra."), 'ok'); setE({}); l.reload()
    } catch (er) { toast((er as ApiError).message, 'crit') } finally { setSalvando(false) }
  }
  async function subir(f: File | undefined) {
    if (!f) return
    setSubindo(true)
    try { const fd = new FormData(); fd.append('arquivo', f); fd.append('alt', p.name)
      await api.postForm(`/site/produtos/${id}/fotos`, fd); toast(tr("Foto salva (WebP, sem a localização do celular)."), 'ok'); l.reload() }
    catch (er) { toast((er as ApiError).message, 'crit') } finally { setSubindo(false) }
  }
  const moverFoto = (i: number, passo: number) => { const n = [...fotos]; const [f] = n.splice(i, 1); n.splice(i + passo, 0, f); muda({ images: n }) }
  const mudaVar = (i: number, x: Partial<(typeof vars)[number]>) => muda({ variations: vars.map((v, j) => j === i ? { ...v, ...x } : v) })
  return <div className="stack" style={{ gap: 14 }}>
    <div className="row wrap" style={{ gap: 8 }}>
      <Link className="btn sm ghost" to="/site/produtos">{tr("← Produtos")}</Link>
      <div className="grow" />
      {p.active && <a className="btn sm ghost" href={`/store/p/${p.slug}/`} target="_blank" rel="noreferrer">{tr("Ver no site ↗")}</a>}
    </div>
    <section className="card"><div className="card-h"><h2 className="h2" style={{ overflowWrap: 'anywhere' }}>{p.name}</h2></div>
      <div className="card-b stack" style={{ gap: 14 }}>
        <div className="row wrap" style={{ gap: 6 }}>
          <Chip tone={p.active ? 'ok' : 'neutral'}>{p.active ? tr("à venda") : tr("escondido")}</Chip>
          <span className="small muted" style={{ overflowWrap: 'anywhere' }}>/store/p/{p.slug}/{p.updated_at ? ` · ${tr("mudado em {0}", fmtDateTime(p.updated_at))}` : ''}</span></div>
        <div className="loja-grade">
          <label className="fld" style={{ gridColumn: '1 / -1' }}><span>{tr("Nome")} <i>{tr("o cliente lê, em inglês")}</i></span>
            <input value={e.name ?? p.name} disabled={!gerente} onChange={x => muda({ name: x.target.value })} /></label>
          {!vars.length && <>
            <label className="fld"><span>{tr("Preço (US$)")} <i>{tr("0 = sob consulta")}</i></span>
              <input inputMode="decimal" value={e.regular ?? txt(p.regular)} disabled={!gerente} onChange={x => muda({ regular: x.target.value })} /></label>
            <label className="fld"><span>{tr("Preço promocional")} <i>{tr("opcional")}</i></span>
              <input inputMode="decimal" value={e.promo ?? promoDe(p.price, p.regular)} disabled={!gerente} onChange={x => muda({ promo: x.target.value })} /></label>
          </>}
          <label className="fld"><span>{tr("Frete por unidade (US$)")} <i>{tr("vazio = combinar à parte; 0 = grátis")}</i></span>
            <input inputMode="decimal" value={e.shipping_fee ?? txt(p.shipping_fee)} disabled={!gerente} onChange={x => muda({ shipping_fee: x.target.value })} /></label>
          <label className="fld"><span>{tr("Depósito de segurança por unidade (US$)")} <i>{tr("0 = sem")}</i></span>
            <input inputMode="decimal" value={e.deposit ?? txt(p.deposit)} disabled={!gerente} onChange={x => muda({ deposit: x.target.value })} /></label>
          <label className="fld"><span>{tr("SKU")} <i>{tr("opcional")}</i></span>
            <input value={e.sku ?? p.sku} disabled={!gerente} onChange={x => muda({ sku: x.target.value })} /></label>
          <label className="fld"><span>{tr("Como vendemos")} <i>{tr("interno: o cliente não vê")}</i></span>
            <select value={e.fulfillment ?? p.fulfillment} disabled={!gerente} onChange={x => muda({ fulfillment: x.target.value as Fulfillment })}>
              <option value="dropshipping">{tr("Dropshipping (o fornecedor envia)")}</option>
              <option value="estoque">{tr("Em estoque (o box envia)")}</option></select></label>
          {!vars.length && ligado('') ? <div className="check loja-check loja-estoque">
            <input type="checkbox" checked={ligado('')!.tem >= 1} disabled aria-label={tr("Em estoque (pelo estoque)")} />
            <span>{tr("Em estoque: tem {0} {1} (Galpão + Pista)", qtd(ligado('')!.tem), ligado('')!.unit)} · <Link to={`/site/estoque/${p.slug}`}>{tr("Estoque do site")}</Link></span></div>
            : <label className="check loja-check"><input type="checkbox" checked={e.in_stock ?? p.in_stock} disabled={!gerente} onChange={x => muda({ in_stock: x.target.checked })} /> {tr("Em estoque")}</label>}
        </div>
        {emEstoque && vars.length > 0 && <p className="small muted" style={{ margin: 0 }}>{tr("Com opções, a caixa \"Em estoque\" do produto vale para as opções sem item ligado (desmarcada, nenhuma delas vende); as ligadas seguem o estoque.")}</p>}
        {emEstoque && !Object.keys(ligados).length && <p className="small muted" style={{ margin: 0 }}>{tr("Em estoque, mas ainda sem item ligado: até ligar, o site segue a caixa \"Em estoque\".")} <Link to={`/site/estoque/${p.slug}`}>{tr("Ligar em Estoque do site")}</Link></p>}
      </div>
    </section>

    <Section title={tr("Categorias")}>
      <div className="row wrap" style={{ gap: 8 }}>{l.data.categorias.map(c => <label key={c.slug} className="check loja-check">
        <input type="checkbox" checked={cats.includes(c.slug)} disabled={!gerente}
          onChange={x => muda({ categories: x.target.checked ? [...cats, c.slug] : cats.filter(s => s !== c.slug) })} /> {c.name}</label>)}</div>
    </Section>

    <Section title={tr("Fotos")} count={fotos.length}>
      <p className="small muted" style={{ marginTop: 0 }}>{tr("A primeira é a da loja. A foto sobe em WebP de até 1600 px, sem a localização do celular.")}</p>
      <ul className="loja-fotos">{fotos.map((f, i) => <li key={f.src + i} className="card card-b">
        <img src={fotoUrl(f.src)} alt={f.alt} width={160} height={160} loading="lazy" />
        <label className="fld"><span>{tr("Descrição da foto")}</span>
          <input value={f.alt} disabled={!gerente} onChange={x => muda({ images: fotos.map((g, j) => j === i ? { ...g, alt: x.target.value } : g) })} /></label>
        {gerente && <div className="row wrap" style={{ gap: 6 }}>
          <button className="btn sm ghost" aria-label={tr("Foto para a frente")} disabled={i === 0} onClick={() => moverFoto(i, -1)}>←</button>
          <button className="btn sm ghost" aria-label={tr("Foto para trás")} disabled={i === fotos.length - 1} onClick={() => moverFoto(i, 1)}>→</button>
          <button className="btn sm ghost" onClick={() => muda({ images: fotos.filter((_, j) => j !== i) })}>{tr("Tirar")}</button></div>}
      </li>)}</ul>
      {gerente && <label className="btn sm" style={{ marginTop: 10 }}>{subindo ? tr("Subindo…") : tr("Subir foto")}
        <input type="file" accept="image/*" className="sr-only" disabled={subindo || !!e.images} onChange={x => { subir(x.target.files?.[0]); x.target.value = '' }} /></label>}
      {e.images && <p className="small muted">{tr("Salve a ordem das fotos antes de subir outra.")}</p>}
    </Section>

    <Section title={tr("Texto")}>
      <div className="loja-grade">
        <EditorTexto id={`resumo-${id}`} rotulo={tr("Resumo")} valor={e.short ?? p.short} disabled={!gerente} onChange={h => muda({ short: h })} />
        <EditorTexto id={`descricao-${id}`} rotulo={tr("Descrição")} valor={e.description ?? p.description} disabled={!gerente} onChange={h => muda({ description: h })} />
      </div>
    </Section>

    <Section title={tr("Opções (tamanho, cor…)")} count={vars.length}>
      <p className="small muted" style={{ marginTop: 0 }}>{tr("Cada opção tem o seu preço. Com duas escolhas, separe com \" / \" (ex.: Blue / 2). Sem opção, vale o preço do produto.")}</p>
      {vars.length > 0 && <label className="fld"><span>{tr("Nome da escolha")} <i>{tr("ex.: Size, ou Color / Number of Sponsors")}</i></span>
        <input value={nomes.join(' / ')} disabled={!gerente} onChange={x => muda({ attribute_names: x.target.value.split('/').map(s => s.trim()) })} /></label>}
      <div className="stack" style={{ gap: 8, marginTop: 8 }}>{vars.map((v, i) => <div key={i} className="loja-var">
        <label className="fld"><span>{tr("Opção")}</span><input value={v.attrs.join(' / ')} disabled={!gerente} onChange={x => mudaVar(i, { attrs: x.target.value.split('/').map(s => s.trim()) })} /></label>
        <label className="fld"><span>{tr("Preço (US$)")}</span><input inputMode="decimal" value={v.regular} disabled={!gerente} onChange={x => mudaVar(i, { regular: x.target.value })} /></label>
        <label className="fld"><span>{tr("Promocional")}</span><input inputMode="decimal" value={v.promo} disabled={!gerente} onChange={x => mudaVar(i, { promo: x.target.value })} /></label>
        {ligado(v.attrs.join(' / ')) ? <div className="check loja-check loja-estoque">
          <input type="checkbox" checked={ligado(v.attrs.join(' / '))!.tem >= 1} disabled aria-label={tr("Em estoque (pelo estoque)")} />
          <span>{tr("tem {0}", qtd(ligado(v.attrs.join(' / '))!.tem))}</span></div>
          : <label className="check loja-check"><input type="checkbox" checked={v.in_stock} disabled={!gerente} onChange={x => mudaVar(i, { in_stock: x.target.checked })} /> {tr("Em estoque")}</label>}
        {gerente && <button className="btn sm ghost" onClick={() => muda({ variations: vars.filter((_, j) => j !== i) })}>{tr("Tirar")}</button>}
      </div>)}</div>
      {gerente && <button className="btn sm ghost" style={{ marginTop: 8 }} onClick={() => muda({ variations: [...vars, { attrs: [''], regular: txt(p.regular), promo: '', in_stock: true, antes: null }] })}>{tr("+ Opção")}</button>}
    </Section>

    {gerente && <div className="loja-salvar card card-b row wrap" style={{ gap: 8 }}>
      <button className="btn primary" disabled={!mudou || salvando} onClick={() => salvar()}>{salvando ? tr("Salvando…") : tr("Salvar")}</button>
      {mudou && <button className="btn ghost" onClick={() => setE({})}>{tr("Desfazer")}</button>}
      <div className="grow" />
      <button className="btn ghost" disabled={salvando} onClick={() => salvar({ active: !p.active })}>{p.active ? tr("Esconder da loja") : tr("Pôr à venda")}</button>
    </div>}
  </div>
}
