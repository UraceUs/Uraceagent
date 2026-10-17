/* #172 · Site › Blog (dono, 16/10: "editor do blog, pode seguir"). Os artigos do blog do site, em rascunho ou no ar.
 * O OPERATOR escreve o rascunho; só o ADMIN (ou a conta de acesso livre) publica e tira do ar. "Novo artigo" fica em
 * cima (o dono pediu toda inserção no topo); embaixo, os artigos no cartão do padrão D do painel, paginados no servidor.
 * O artigo abre no próprio endereço (/site/blog/12): título, categoria, endereço, resumo, o que o Google mostra, capa,
 * texto com links e fotos, a prévia no visual do site, publicar e as versões.
 * Revisão do #172: Publicar manda `visto` (o `updated_at` do rascunho que a tela abriu). Se o operador salvou outro
 * texto depois, o servidor responde 409 e nada vai ao ar: a tela recarrega o artigo e a prévia e avisa. */
import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { useGet } from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import { Chip, Empty, ErrorState, Loading, Section } from '../components/ui'
import { EditorTexto } from '../components/EditorTexto'
import { usePerguntar } from '../components/Perguntar'
import { Cartao } from '../components/Cartao'
import { useToast } from '../components/Toast'
import { fmtDate, fmtDateTime } from '../components/fmt'
import { tr } from '../i18n'

type Estado = 'rascunho' | 'no_ar' | 'mudou'
interface Conteudo { title: string; seo_title: string; excerpt: string; description: string; category: string; image: string
  image_alt: string; image_w: number | null; image_h: number | null; html: string }
interface Post { id: number; slug: string; category: string; origin: string | null; estado: Estado; draft: Conteudo
  published: Conteudo | null; first_published_at: string | null; published_at: string | null; publicado_por: string | null
  updated_at: string | null; mudado_por: string | null; created_at: string; endereco: string; endereco_travado: boolean; no_google: boolean }
interface Categoria { slug: string; name: string }
interface Lista { posts: Post[]; total: number; limit: number; offset: number; categorias: Categoria[] }
interface Saida { post: Post; problemas: string[]; previa: string; categorias: Categoria[] }
interface Versao { id: number; published_at: string; por: string | null; original: boolean; title: string }

const POR_PAGINA = 20
const ESTADO: Record<Estado, [string, 'ok' | 'info' | 'warn']> = {
  rascunho: [tr("rascunho"), 'warn'], no_ar: [tr("no ar"), 'ok'], mudou: [tr("mudado depois de publicar"), 'info'] }
/** A foto no painel: as do site moram em /_s/img; as subidas aqui já vêm com o caminho (/_f/…). */
const fotoUrl = (src: string) => src.startsWith('/') ? src : `/_s/img/${src}`
const nomeDa = (cats: Categoria[], slug: string) => cats.find(c => c.slug === slug)?.name || slug

export function ArtigosDoBlog() {
  const nav = useNavigate()
  const toast = useToast()
  const [q, setQ] = useState('')
  const [busca, setBusca] = useState('')
  const [estado, setEstado] = useState('')
  const [categoria, setCategoria] = useState('')
  const [offset, setOffset] = useState(0)
  const [novo, setNovo] = useState({ title: '', category: 'training-racing' })
  const [criando, setCriando] = useState(false)
  const qs = new URLSearchParams({ limit: String(POR_PAGINA), offset: String(offset), ...(busca ? { q: busca } : {}),
    ...(estado ? { estado } : {}), ...(categoria ? { categoria } : {}) })
  const l = useGet<Lista>(`/site/blog?${qs}`)
  const cats = l.data?.categorias || []
  async function criar(e: FormEvent) {
    e.preventDefault()
    setCriando(true)
    try {
      const r = await api.post<{ id: number }>('/site/blog', novo)
      toast(tr("Rascunho criado: escreva e salve. O site só mostra depois que o administrador publicar."), 'ok')
      nav(`/site/blog/${r.id}`)
    } catch (er) { toast((er as ApiError).message, 'crit') } finally { setCriando(false) }
  }
  return <div className="stack" style={{ gap: 14 }}>
    <Section title={tr("Novo artigo")}>
      <form className="loja-grade" onSubmit={criar}>
        <label className="fld"><span>{tr("Título do artigo")} <i>{tr("o leitor lê, em inglês")}</i></span>
          <input value={novo.title} maxLength={120} onChange={e => setNovo({ ...novo, title: e.target.value })} /></label>
        <label className="fld"><span>{tr("Categoria do artigo")}</span>
          <select value={novo.category} onChange={e => setNovo({ ...novo, category: e.target.value })}>
            {cats.map(c => <option key={c.slug} value={c.slug}>{c.name}</option>)}</select></label>
        <div><button className="btn primary" disabled={novo.title.trim().length < 3 || criando}>{criando ? tr("Criando…") : tr("Criar e abrir")}</button></div>
      </form>
    </Section>
    <Section title={tr("Artigos")} count={l.data?.total}>
      <div className="stack" style={{ gap: 12 }}>
        <p className="small muted" style={{ margin: 0 }}>{tr("O blog do site (/blog/). Publicado, o artigo entra na hora no blog, na categoria e no mapa do site; quem já abriu a página vê a nova em até 5 minutos, e o Google relê o mapa do site em até 24 horas.")}</p>
        <form className="loja-filtros" role="search" onSubmit={e => { e.preventDefault(); setBusca(q.trim()); setOffset(0) }}>
          <label className="fld"><span>{tr("Buscar")}</span><input type="search" value={q} placeholder={tr("título ou endereço")} enterKeyHint="search"
            onChange={e => setQ(e.target.value)} onBlur={() => { if (q.trim() !== busca) { setBusca(q.trim()); setOffset(0) } }} /></label>
          <label className="fld"><span>{tr("Estado")}</span><select value={estado} onChange={e => { setEstado(e.target.value); setOffset(0) }}>
            <option value="">{tr("Todos")}</option><option value="no_ar">{tr("No ar")}</option><option value="rascunho">{tr("Rascunho")}</option>
            <option value="mudou">{tr("Mudado depois de publicar")}</option></select></label>
          <label className="fld"><span>{tr("Categoria")}</span><select value={categoria} onChange={e => { setCategoria(e.target.value); setOffset(0) }}>
            <option value="">{tr("Todas")}</option>{cats.map(c => <option key={c.slug} value={c.slug}>{c.name}</option>)}</select></label>
        </form>
        {l.error && <ErrorState error={l.error} retry={l.reload} />}
        {l.loading && !l.data && <Loading />}
        {l.data && (!l.data.posts.length ? <Empty title={tr("Nenhum artigo aqui")}>{tr("Mude a busca ou os filtros.")}</Empty>
          : <div className="cd-grade">{l.data.posts.map(p => <CartaoArtigo key={p.id} p={p} cats={cats} />)}</div>)}
        {l.data && l.data.total > POR_PAGINA && <div className="row" style={{ gap: 8 }}>
          <button className="btn sm ghost" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - POR_PAGINA))}>{tr("Anteriores")}</button>
          <span className="small muted grow" style={{ textAlign: 'center' }}>{offset + 1}–{Math.min(offset + POR_PAGINA, l.data.total)} {tr("de")} {l.data.total}</span>
          <button className="btn sm ghost" disabled={offset + POR_PAGINA >= l.data.total} onClick={() => setOffset(offset + POR_PAGINA)}>{tr("Próximas")}</button></div>}
      </div>
    </Section>
  </div>
}

function CartaoArtigo({ p, cats }: { p: Post; cats: Categoria[] }) {
  const [rot, tom] = ESTADO[p.estado]
  const d = p.draft
  return <Cartao id={`artigo-${p.id}`} estado={rot} tom={tom}
    capa={d.image ? <img className="cd-capa" src={fotoUrl(d.image)} alt="" width={64} height={64} loading="lazy" /> : null}
    avatar={(d.title.trim()[0] || '#').toUpperCase()} nome={d.title}
    sub={[`${nomeDa(cats, p.category)}${p.first_published_at ? ` · ${fmtDate(p.first_published_at.slice(0, 10))}` : ''}`]}
    detalhe={p.endereco}
    acoes={<>
      <Link className="btn primary" to={`/site/blog/${p.id}`}>{tr("Abrir")}</Link>
      {p.estado !== 'rascunho' && <a className="btn ghost" href={p.endereco} target="_blank" rel="noreferrer">{tr("Ver no site ↗")}</a>}</>}>
    <ul className="cd-lista">
      {p.published_at && <li><i className={`cd-ic ${p.estado === 'rascunho' ? 'warn' : 'ok'}`} aria-hidden="true">{p.estado === 'rascunho' ? '–' : '✓'}</i>
        <span className="grow">{p.estado === 'rascunho' ? tr("Fora do ar (já foi publicado)") : tr("Publicado")}</span>
        <span className="muted">{p.publicado_por ? `${p.publicado_por} · ` : ''}{p.published_at.length <= 10 ? fmtDate(p.published_at) : fmtDateTime(p.published_at)}</span></li>}
      {!p.published_at && <li><i className="cd-ic warn" aria-hidden="true">…</i><span className="grow">{tr("Nunca foi ao ar")}</span></li>}
      {p.updated_at && <li><i className="cd-ic info" aria-hidden="true">i</i><span className="grow">{tr("Rascunho mudado")}</span>
        <span className="muted">{p.mudado_por ? `${p.mudado_por} · ` : ''}{fmtDateTime(p.updated_at)}</span></li>}
    </ul>
  </Cartao>
}

type Edicao = Partial<Pick<Conteudo, 'title' | 'seo_title' | 'excerpt' | 'description' | 'category' | 'image_alt' | 'html' | 'image'>> & { slug?: string }

const conta = (t: string, max: number) => <i className={t.length > max ? 'crit' : undefined}>{t.length}/{max}</i>

export function EditarArtigo({ id }: { id: number }) {
  const { can } = useAuth()
  const admin = can('ADMIN')
  const toast = useToast()
  const perguntar = usePerguntar()
  const l = useGet<Saida>(`/site/blog/${id}`)
  const vs = useGet<{ versoes: Versao[] }>(`/site/blog/${id}/versoes`)
  const [saida, setSaida] = useState<Saida | null>(null)
  const [e, setE] = useState<Edicao>({})
  const [indo, setIndo] = useState('')
  const [tela, setTela] = useState<'celular' | 'computador'>('celular')
  const [v, setV] = useState(0)
  const atual = saida || l.data
  if (l.error && !atual) return <ErrorState error={l.error} retry={l.reload} />
  if (!atual) return <Loading />
  const p = atual.post
  const d = p.draft
  const val = <K extends keyof Edicao>(k: K, base: string) => (e[k] ?? base) as string
  const muda = (x: Edicao) => setE(y => ({ ...y, ...x }))
  const mudou = Object.keys(e).length > 0
  const novo = (r: Saida) => { setSaida(r); setV(n => n + 1) }

  async function correr(nome: string, f: () => Promise<Saida | null>, ok: string) {
    setIndo(nome)
    try { const r = await f(); if (r) { novo(r); toast(ok, 'ok') } }
    catch (er) { toast((er as ApiError).message, 'crit') } finally { setIndo('') }
  }
  const salvar = () => correr('salvar', async () => { const r = await api.patch<Saida>(`/site/blog/${id}`, e); setE({}); return r },
    p.estado === 'rascunho' ? tr("Rascunho salvo.") : tr("Rascunho salvo: o site continua com o que está no ar até publicar."))
  // só o que esta tela mostrou vai ao ar: mudou depois que abriu (409), recarrega o artigo e a prévia e avisa
  const publicar = () => correr('publicar', async () => {
    try { const r = await api.post<Saida>(`/site/blog/${id}/publicar`, { visto: p.updated_at }); vs.reload(); return r }
    catch (er) {
      if (!(er instanceof ApiError) || er.status !== 409) throw er
      novo(await api.get<Saida>(`/site/blog/${id}`)); vs.reload()
      toast(tr("O rascunho mudou depois que você abriu o artigo. A tela já mostra o texto novo: confira a prévia e publique de novo."), 'warn')
      return null
    }
  }, tr("Publicado: o blog e o mapa do site já mostram."))
  const despublicar = () => correr('despublicar', async () => {
    const sim = await perguntar(p.no_google
      ? { titulo: tr("Tirar do ar um artigo que já está no Google?"), perigo: true, ok: tr("Tirar do ar"),
          texto: tr("O endereço {0} veio do site antigo e o Google já o tem. Fora do ar, ele dá \"página não encontrada\" (404) para quem chegar pelo Google ou por um link salvo. O rascunho e as versões ficam aqui.", p.endereco) }
      : { titulo: tr("Tirar este artigo do ar?"), ok: tr("Tirar do ar"), texto: tr("O endereço {0} passa a dar 404 e o artigo sai do blog e do mapa do site. O rascunho e as versões ficam aqui.", p.endereco) })
    if (!sim) return null
    return api.post<Saida>(`/site/blog/${id}/despublicar`, { confirmar: true })
  }, tr("O artigo saiu do ar."))
  const voltarVersao = (vid: number) => correr('versao', async () => { const r = await api.post<Saida>(`/site/blog/${id}/versoes/${vid}/voltar`); setE({}); return r },
    tr("A versão voltou para o rascunho: confira na prévia e publique."))
  async function subirCapa(f: File | undefined) {
    if (!f) return
    const fd = new FormData(); fd.append('arquivo', f); fd.append('alt', val('image_alt', d.image_alt))
    await correr('capa', () => api.postForm<Saida>(`/site/blog/${id}/capa`, fd), tr("Capa salva no rascunho (WebP, sem a localização do celular)."))
    setE(y => { const n = { ...y }; delete n.image_alt; delete n.image; return n })
  }
  async function subirImagem(f: File) {
    try { const fd = new FormData(); fd.append('arquivo', f)
      return (await api.postForm<{ src: string }>(`/site/blog/${id}/imagens`, fd)).src }
    catch (er) { toast((er as ApiError).message, 'crit'); return null }
  }
  const capa = e.image === '' ? '' : d.image
  const versoes = vs.data?.versoes || []
  return <div className="stack" style={{ gap: 14 }}>
    <div className="row wrap" style={{ gap: 8 }}>
      <Link className="btn sm ghost" to="/site/blog">{tr("← Artigos")}</Link>
      <div className="grow" />
      <Chip tone={ESTADO[p.estado][1]}>{ESTADO[p.estado][0]}</Chip>
      {p.estado !== 'rascunho' && <a className="btn sm ghost" href={p.endereco} target="_blank" rel="noreferrer">{tr("Ver no site ↗")}</a>}
    </div>
    <section className="card"><div className="card-h"><h2 className="h2" style={{ overflowWrap: 'anywhere' }}>{val('title', d.title) || tr("Sem título")}</h2></div>
      <div className="card-b stack" style={{ gap: 12 }}>
        <div className="loja-grade">
          <label className="fld" style={{ gridColumn: '1 / -1' }}><span>{tr("Título do artigo")} <i>{tr("o título grande da página, em inglês")}</i> {conta(val('title', d.title), 120)}</span>
            <input value={val('title', d.title)} onChange={x => muda({ title: x.target.value })} /></label>
          <label className="fld"><span>{tr("Categoria do artigo")}</span>
            <select value={val('category', d.category)} onChange={x => muda({ category: x.target.value })}>
              {atual.categorias.map(c => <option key={c.slug} value={c.slug}>{c.name}</option>)}</select></label>
          <label className="fld"><span>{tr("Endereço")} <i>{p.endereco_travado ? tr("travado: já foi publicado") : tr("/blog/…/; trava na primeira publicação")}</i></span>
            <input value={e.slug ?? p.slug} disabled={p.endereco_travado} onChange={x => muda({ slug: x.target.value })} /></label>
          <label className="fld" style={{ gridColumn: '1 / -1' }}><span>{tr("Resumo")} <i>{tr("o texto do cartão no blog")}</i> {conta(val('excerpt', d.excerpt), 400)}</span>
            <textarea rows={3} value={val('excerpt', d.excerpt)} onChange={x => muda({ excerpt: x.target.value })} /></label>
          <label className="fld" style={{ gridColumn: '1 / -1' }}><span>{tr("Descrição para o Google")} <i>{tr("50 a 155 letras; o texto embaixo do título no Google")}</i> {conta(val('description', d.description), 155)}</span>
            <textarea rows={2} value={val('description', d.description)} onChange={x => muda({ description: x.target.value })} /></label>
          <label className="fld" style={{ gridColumn: '1 / -1' }}><span>{tr("Título para o Google")} <i>{tr("opcional; vazio, vale o título do artigo")}</i> {conta(val('seo_title', d.seo_title), 70)}</span>
            <input value={val('seo_title', d.seo_title)} onChange={x => muda({ seo_title: x.target.value })} /></label>
        </div>
      </div>
    </section>

    <Section title={tr("Capa")}>
      <div className="blog-capa">
        {capa ? <img src={fotoUrl(capa)} alt={val('image_alt', d.image_alt)} width={d.image_w || 320} height={d.image_h || 180} loading="lazy" />
          : <p className="small muted" style={{ margin: 0 }}>{tr("Sem capa. A foto sobe em WebP de até 1600 px, sem a localização do celular.")}</p>}
        <div className="stack" style={{ gap: 8, minWidth: 0 }}>
          <label className="fld"><span>{tr("Descrição da capa")} <i>{tr("o que a foto mostra; quem não vê a foto ouve este texto")}</i></span>
            <input value={val('image_alt', d.image_alt)} maxLength={200} onChange={x => muda({ image_alt: x.target.value })} /></label>
          <div className="row wrap" style={{ gap: 8 }}>
            <label className="btn sm">{indo === 'capa' ? tr("Subindo…") : capa ? tr("Trocar a capa") : tr("Subir a capa")}
              <input type="file" accept="image/*" className="sr-only" disabled={!!indo} onChange={x => { subirCapa(x.target.files?.[0]); x.target.value = '' }} /></label>
            {capa && <button type="button" className="btn sm ghost" onClick={() => muda({ image: '' })}>{tr("Tirar a capa")}</button>}
          </div>
        </div>
      </div>
    </Section>

    <Section title={tr("Texto")}>
      <p className="small muted" style={{ marginTop: 0 }}>{tr("Títulos, listas, links e fotos. Tabelas e citações que já estão no texto ficam como estão.")}</p>
      <EditorTexto id={`blog-${id}`} rotulo={tr("Texto do artigo")} valor={val('html', d.html)} onChange={h => muda({ html: h })} link imagem={subirImagem} />
    </Section>

    {atual.problemas.length > 0 && <div className="ed-problemas" role="status"><b>{tr("Antes de publicar, falta:")}</b><ul>{atual.problemas.map(x => <li key={x}>{x}</li>)}</ul></div>}

    <Section title={tr("Prévia")}>
      <p className="small muted" style={{ marginTop: 0 }}>{tr("O rascunho salvo, no visual do site (fora do Google).")}</p>
      <div className="seg" role="group" aria-label={tr("Tamanho da prévia")} style={{ marginBottom: 8 }}>
        <button className={`btn sm${tela === 'celular' ? '' : ' ghost'}`} aria-pressed={tela === 'celular'} onClick={() => setTela('celular')}>{tr("Celular")}</button>
        <button className={`btn sm${tela === 'computador' ? '' : ' ghost'}`} aria-pressed={tela === 'computador'} onClick={() => setTela('computador')}>{tr("Computador")}</button>
      </div>
      <div className="blog-previa"><iframe key={v} className={`ed-iframe blog-iframe-${tela}`} title={tr("Prévia do artigo")} src={`${atual.previa}?v=${v}`} /></div>
    </Section>

    <Section title={tr("Versões publicadas")} count={versoes.length}>
      {!versoes.length ? <p className="small muted" style={{ margin: 0 }}>{p.origin === 'wordpress' ? tr("Veio do site antigo; cada publicação daqui guarda uma versão.") : tr("Ainda não foi publicado.")}</p>
        : <ul className="cd-lista">{versoes.map(x => <li key={x.id}><span className="grow">{x.title}<span className="muted"> · {x.original ? tr("site antigo") : x.por || '—'} · {x.published_at.length <= 10 ? fmtDate(x.published_at) : fmtDateTime(x.published_at)}</span></span>
          <button className="btn sm ghost" disabled={!!indo} onClick={() => voltarVersao(x.id)}>{tr("Voltar a esta versão")}</button></li>)}</ul>}
    </Section>

    <div className="loja-salvar card card-b row wrap" style={{ gap: 8 }}>
      <button className="btn primary" disabled={!mudou || !!indo} onClick={salvar}>{indo === 'salvar' ? tr("Salvando…") : tr("Salvar rascunho")}</button>
      {mudou && <button className="btn ghost" disabled={!!indo} onClick={() => setE({})}>{tr("Desfazer")}</button>}
      <div className="grow" />
      {admin ? <>
        <button className="btn" disabled={mudou || !!indo || atual.problemas.length > 0 || p.estado === 'no_ar'} title={mudou ? tr("Salve o rascunho antes de publicar") : undefined}
          onClick={publicar}>{indo === 'publicar' ? tr("Publicando…") : p.estado === 'mudou' ? tr("Publicar as mudanças") : tr("Publicar")}</button>
        {p.published && <button className="btn ghost" disabled={!!indo} onClick={despublicar}>{tr("Tirar do ar")}</button>}
      </> : <span className="small muted">{tr("Só o administrador publica: salve o rascunho e avise.")}</span>}
    </div>
  </div>
}
