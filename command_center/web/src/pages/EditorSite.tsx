/* Editor visual do site (#300). Dono, 16/10: "como alterar o design, layout, puxando e arrastando e soltando de uma
 * forma bem simples e conseguir editar por lá como se fosse realmente um WordPress". Decisão: livre, tipo Elementor.
 * A página é uma lista de seções (1 a 3 colunas, cada uma com os seus elementos) e, numa página que já existe, as
 * faixas originais dela. Arrastar e soltar no computador; no celular e no teclado, os botões ↑ ↓. O rascunho salva
 * sozinho; a pré-visualização é o site de verdade; publicar confere as regras do site e guarda uma versão. */
import { useEffect, useRef, useState, type DragEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { useGet } from '../api/hooks'
import { useAuth } from '../auth/AuthContext'
import { Chip, Empty, ErrorState, Loading, Section } from '../components/ui'
import { EditorTexto } from '../components/EditorTexto'
import { useToast } from '../components/Toast'
import { fmtDateTime } from '../components/fmt'
import { tr } from '../i18n'

type Tipo = 'titulo' | 'texto' | 'imagem' | 'botao' | 'lista' | 'espaco' | 'karts' | 'produtos' | 'cartoes' | 'faq'
interface Faq { pergunta: string; resposta: string }
interface W { id: string; tipo: Tipo; texto?: string; nivel?: number; tamanho?: string; cor?: string; alinhar?: string; html?: string
  src?: string; alt?: string; forma?: string; largura?: number; altura?: number; legenda?: string; link?: string; estilo?: string
  itens?: (string | Faq)[]; categoria?: string; quantos?: number; pagina?: string }
interface Secao { id: string; tipo: 'secao'; fundo: string; espaco: string; colunas: number; itens: W[][] }
interface Original { id: string; tipo: 'original'; indice: number; oculto: boolean }
type Item = Secao | Original
interface Conteudo { itens: Item[] }
interface Pagina { id: number; path: string; base: string | null; title: string; description: string; draft: Conteudo
  published: Conteudo | null; estado: 'rascunho' | 'publicada' | 'mudou'; published_at: string | null; updated_at: string | null }
interface Saida { pagina: Pagina; problemas: string[]; originais: string[]; previa: string }

const ESTADO: Record<string, [string, 'neutral' | 'ok' | 'warn']> = {
  rascunho: [tr("rascunho, fora do ar"), 'neutral'], publicada: [tr("no ar"), 'ok'], mudou: [tr("no ar, com mudanças não publicadas"), 'warn'] }
const NOMES: Record<Tipo, string> = { titulo: tr("Título"), texto: tr("Texto"), imagem: tr("Imagem"), botao: tr("Botão"), lista: tr("Lista"),
  espaco: tr("Espaço"), karts: tr("Karts e preços"), produtos: tr("Produtos da loja"), cartoes: tr("Cartões de uma página"), faq: tr("Perguntas frequentes") }
const PALETA: Tipo[] = ['titulo', 'texto', 'imagem', 'botao', 'lista', 'espaco', 'karts', 'produtos', 'cartoes', 'faq']
const FUNDOS: [string, string][] = [['clara', tr("Claro")], ['escura', tr("Escuro")], ['marca', tr("Vermelho")], ['cinza', tr("Cinza")]]
const PG_CARTOES: [string, string][] = [['academy', 'Academy'], ['pro-team', 'Pro Team'], ['for-beginners', 'For Beginners']]
const CATS: [string, string][] = [['', tr("Todas")], ['chassis', 'Chassis'], ['competition-karts', 'Competition karts'], ['engines', 'Engines'],
  ['parts', 'Parts'], ['tires', 'Tires'], ['custom-kart-suits', 'Custom kart suits'], ['official-urace-products', 'Official URACE products'],
  ['kart-driver-training', 'Programs']]
const novoId = () => Math.random().toString(16).slice(2, 10)

function novoWidget(t: Tipo): W {
  const id = novoId()
  switch (t) {
    case 'titulo': return { id, tipo: t, texto: 'New title', nivel: 2, tamanho: 'm', cor: 'padrao', alinhar: 'esq' }
    case 'texto': return { id, tipo: t, html: '<p>Write here.</p>', tamanho: 'm', cor: 'padrao', alinhar: 'esq' }
    case 'botao': return { id, tipo: t, texto: 'Book now', link: '/services/arrive-and-drive/#reservar', estilo: 'cheio', alinhar: 'esq' }
    case 'lista': return { id, tipo: t, itens: ['First item'] }
    case 'espaco': return { id, tipo: t, tamanho: 'm' }
    case 'produtos': return { id, tipo: t, categoria: '', quantos: 6 }
    case 'cartoes': return { id, tipo: t, pagina: 'academy' }
    case 'faq': return { id, tipo: t, itens: [{ pergunta: 'Question?', resposta: 'Answer.' }] }
    default: return { id, tipo: t }
  }
}
const novaSecao = (): Secao => ({ id: novoId(), tipo: 'secao', fundo: 'clara', espaco: 'm', colunas: 1, itens: [[]] })
const resumo = (w: W) => w.tipo === 'titulo' ? `h${w.nivel} · ${w.texto}` : w.tipo === 'texto' ? (w.html || '').replace(/<[^>]+>/g, ' ').trim().slice(0, 80)
  : w.tipo === 'botao' ? `${w.texto} → ${w.link}` : w.tipo === 'imagem' ? (w.alt || tr("sem descrição")) : w.tipo === 'lista' ? `${(w.itens || []).length} ${tr("itens")}`
  : w.tipo === 'faq' ? `${(w.itens || []).length} ${tr("perguntas")}` : w.tipo === 'cartoes' ? (w.pagina || '') : w.tipo === 'produtos' ? `${w.quantos} · ${w.categoria || tr("todas")}` : ''

// ------------------------------------------------------------------ a lista de páginas
export function PaginasDoEditor() {
  const { can } = useAuth()
  const nav = useNavigate()
  const toast = useToast()
  const l = useGet<{ paginas: Pick<Pagina, 'id' | 'path' | 'base' | 'title' | 'estado' | 'published_at' | 'updated_at'>[]; existentes: { caminho: string; titulo: string }[] }>('/site/editor/paginas')
  const [nova, setNova] = useState({ title: '', path: '' })
  async function criar(corpo: Record<string, string>) {
    try { const r = await api.post<Saida>('/site/editor/paginas', corpo); toast(tr("Página aberta no editor: nada muda no site até publicar."), 'ok'); nav(`/site/editor/${r.pagina.id}`) }
    catch (er) { toast((er as ApiError).message, 'crit') }
  }
  if (l.error && !l.data) return <ErrorState error={l.error} retry={l.reload} />
  if (!l.data) return <Loading />
  return <div className="stack" style={{ gap: 14 }}>
    <p className="small muted" style={{ margin: 0 }}>{tr("Monte páginas do site arrastando seções e elementos. Numa página que já existe, as faixas dela viram blocos que se movem ou se escondem. Nada muda no site até você publicar; cada publicação guarda uma versão para voltar.")}</p>
    <Section title={tr("Páginas no editor")} count={l.data.paginas.length}>
      {!l.data.paginas.length ? <Empty title={tr("Nenhuma página ainda")}>{tr("Abra uma página do site ou crie uma nova.")}</Empty>
        : <ul className="ed-lista-paginas">{l.data.paginas.map(p => <li key={p.id} className="card card-b">
          <div className="grow" style={{ minWidth: 0 }}><Link className="loja-nome" to={`/site/editor/${p.id}`}>{p.title}</Link>
            <div className="small muted" style={{ overflowWrap: 'anywhere' }}>{p.path}{p.base ? ` · ${tr("página do site")}` : ` · ${tr("página nova")}`}{p.updated_at ? ` · ${fmtDateTime(p.updated_at)}` : ''}</div></div>
          <Chip tone={ESTADO[p.estado][1]}>{ESTADO[p.estado][0]}</Chip>
          <Link className="btn sm ghost" to={`/site/editor/${p.id}`}>{tr("Editar")}</Link></li>)}</ul>}
    </Section>
    {can('MANAGER') && <>
      <Section title={tr("Nova página")}>
        <div className="loja-grade">
          <label className="fld"><span>{tr("Título da aba")} <i>{tr("o cliente lê, em inglês")}</i></span><input value={nova.title} onChange={e => setNova({ ...nova, title: e.target.value })} /></label>
          <label className="fld"><span>{tr("Endereço")} <i>{tr("ex.: /summer-camp/ (vazio: sai do título)")}</i></span><input value={nova.path} onChange={e => setNova({ ...nova, path: e.target.value })} /></label>
          <div><button className="btn primary" disabled={nova.title.trim().length < 3} onClick={() => criar(nova)}>{tr("Criar e abrir")}</button></div>
        </div>
      </Section>
      <Section title={tr("Abrir uma página do site")} count={l.data.existentes.length}>
        <ul className="ed-lista-paginas">{l.data.existentes.map(x => <li key={x.caminho} className="card card-b">
          <div className="grow" style={{ minWidth: 0 }}><b style={{ overflowWrap: 'anywhere' }}>{x.titulo}</b><div className="small muted">{x.caminho}</div></div>
          <button className="btn sm ghost" onClick={() => criar({ base: x.caminho })}>{tr("Abrir no editor")}</button></li>)}</ul>
      </Section>
    </>}
  </div>
}

// ------------------------------------------------------------------ o formulário de cada elemento
function Opcoes({ rotulo, valor, opcoes, onChange, disabled }: { rotulo: string; valor: string; opcoes: [string, string][]; onChange: (v: string) => void; disabled?: boolean }) {
  return <label className="fld"><span>{rotulo}</span><select value={valor} disabled={disabled} onChange={e => onChange(e.target.value)}>
    {opcoes.map(([v, n]) => <option key={v} value={v}>{n}</option>)}</select></label>
}
const TAM: [string, string][] = [['p', tr("Pequeno")], ['m', tr("Médio")], ['g', tr("Grande")]]
const COR: [string, string][] = [['padrao', tr("Padrão")], ['marca', tr("Vermelho da marca")], ['suave', tr("Cinza suave")]]
const ALI: [string, string][] = [['esq', tr("À esquerda")], ['centro', tr("No centro")]]

function FormWidget({ w, muda, gerente }: { w: W; muda: (x: Partial<W>) => void; gerente: boolean }) {
  const toast = useToast()
  const d = !gerente
  const estilo = <>{w.tipo !== 'botao' && <Opcoes rotulo={tr("Tamanho")} valor={w.tamanho || 'm'} opcoes={TAM} disabled={d} onChange={v => muda({ tamanho: v })} />}
    {w.tipo !== 'botao' && <Opcoes rotulo={tr("Cor")} valor={w.cor || 'padrao'} opcoes={COR} disabled={d} onChange={v => muda({ cor: v })} />}
    <Opcoes rotulo={tr("Alinhamento")} valor={w.alinhar || 'esq'} opcoes={ALI} disabled={d} onChange={v => muda({ alinhar: v })} /></>
  async function trocarFoto(f: File | undefined) {
    if (!f) return
    try { const fd = new FormData(); fd.append('arquivo', f); const r = await api.postForm<{ src: string; largura: number; altura: number }>('/site/editor/fotos', fd)
      muda({ src: r.src, largura: r.largura, altura: r.altura }); toast(tr("Foto salva (WebP, sem a localização do celular)."), 'ok') }
    catch (er) { toast((er as ApiError).message, 'crit') }
  }
  switch (w.tipo) {
    case 'titulo': return <div className="loja-grade">
      <label className="fld" style={{ gridColumn: '1 / -1' }}><span>{tr("Texto do título")}</span><input value={w.texto || ''} disabled={d} onChange={e => muda({ texto: e.target.value })} /></label>
      <Opcoes rotulo={tr("Nível")} valor={String(w.nivel || 2)} opcoes={[['1', tr("1 · o título da página (um só)")], ['2', tr("2 · título de seção")], ['3', tr("3 · subtítulo")]]} disabled={d} onChange={v => muda({ nivel: Number(v) })} />
      {estilo}</div>
    case 'texto': return <div className="loja-grade"><EditorTexto id={`tx-${w.id}`} rotulo={tr("Texto")} valor={w.html || ''} disabled={d} onChange={h => muda({ html: h })} />{estilo}</div>
    case 'imagem': return <div className="loja-grade">
      {w.src && <img className="ed-mini" src={w.src.startsWith('/') ? w.src : `/_s/img/${w.src}`} alt="" />}
      <label className="fld" style={{ gridColumn: '1 / -1' }}><span>{tr("Descrição da foto")} <i>{tr("o que ela mostra, em inglês")}</i></span><input value={w.alt || ''} disabled={d} onChange={e => muda({ alt: e.target.value })} /></label>
      <Opcoes rotulo={tr("Formato")} valor={w.forma || 'larga'} opcoes={[['larga', tr("Largura toda")], ['media', tr("Média")], ['quadrada', tr("Quadrada")]]} disabled={d} onChange={v => muda({ forma: v })} />
      <label className="fld"><span>{tr("Legenda")} <i>{tr("opcional")}</i></span><input value={w.legenda || ''} disabled={d} onChange={e => muda({ legenda: e.target.value })} /></label>
      {gerente && <label className="btn sm">{tr("Trocar a foto")}<input type="file" accept="image/*" className="sr-only" onChange={e => { trocarFoto(e.target.files?.[0]); e.target.value = '' }} /></label>}
    </div>
    case 'botao': return <div className="loja-grade">
      <label className="fld"><span>{tr("Texto do botão")}</span><input value={w.texto || ''} disabled={d} onChange={e => muda({ texto: e.target.value })} /></label>
      <label className="fld"><span>{tr("Link")} <i>{tr("ex.: /contact/ ou https://")}</i></span><input value={w.link || ''} disabled={d} onChange={e => muda({ link: e.target.value })} /></label>
      <Opcoes rotulo={tr("Estilo")} valor={w.estilo || 'cheio'} opcoes={[['cheio', tr("Cheio (vermelho)")], ['linha', tr("Contorno")]]} disabled={d} onChange={v => muda({ estilo: v })} />
      {estilo}</div>
    case 'lista': return <label className="fld"><span>{tr("Itens (um por linha)")}</span>
      <textarea rows={4} value={(w.itens as string[] || []).join('\n')} disabled={d} onChange={e => muda({ itens: e.target.value.split('\n') })} /></label>
    case 'espaco': return <Opcoes rotulo={tr("Altura")} valor={w.tamanho || 'm'} opcoes={TAM} disabled={d} onChange={v => muda({ tamanho: v })} />
    case 'karts': return <p className="small muted" style={{ margin: 0 }}>{tr("Os karts do Arrive and Drive, com o nome e o preço de Serviços e preços. Mudou lá, muda aqui.")}</p>
    case 'produtos': return <div className="loja-grade">
      <Opcoes rotulo={tr("Categoria")} valor={w.categoria || ''} opcoes={CATS} disabled={d} onChange={v => muda({ categoria: v })} />
      <Opcoes rotulo={tr("Quantos")} valor={String(w.quantos || 6)} opcoes={[3, 4, 6, 8, 12].map(n => [String(n), String(n)])} disabled={d} onChange={v => muda({ quantos: Number(v) })} />
      <p className="small muted" style={{ gridColumn: '1 / -1', margin: 0 }}>{tr("Os produtos à venda, com o preço e a foto de Produtos da loja.")}</p></div>
    case 'cartoes': return <div className="loja-grade"><Opcoes rotulo={tr("Página")} valor={w.pagina || 'academy'} opcoes={PG_CARTOES} disabled={d} onChange={v => muda({ pagina: v })} />
      <p className="small muted" style={{ margin: 0 }}>{tr("Os cartões de preço dessa página, como estão em Cartões das páginas.")}</p></div>
    case 'faq': {
      const itens = (w.itens as Faq[]) || []
      return <div className="stack" style={{ gap: 8 }}>{itens.map((x, i) => <div key={i} className="loja-grade">
        <label className="fld"><span>{tr("Pergunta")}</span><input value={x.pergunta} disabled={d} onChange={e => muda({ itens: itens.map((y, j) => j === i ? { ...y, pergunta: e.target.value } : y) })} /></label>
        <label className="fld"><span>{tr("Resposta")}</span><textarea rows={2} value={x.resposta} disabled={d} onChange={e => muda({ itens: itens.map((y, j) => j === i ? { ...y, resposta: e.target.value } : y) })} /></label>
        {gerente && <div><button className="btn sm ghost" onClick={() => muda({ itens: itens.filter((_, j) => j !== i) })}>{tr("Tirar")}</button></div>}</div>)}
        {gerente && <div><button className="btn sm ghost" onClick={() => muda({ itens: [...itens, { pergunta: '', resposta: '' }] })}>{tr("+ Pergunta")}</button></div>}</div>
    }
  }
  return null
}

// ------------------------------------------------------------------ o editor
/** O navegador só começa o arrasto com algo no dataTransfer (o estado de verdade fica no React). */
function marcar(e: DragEvent, valor: string) { e.dataTransfer.setData('text/plain', valor); e.dataTransfer.effectAllowed = 'move' }
type Arrasto = { tipo: 'widget'; s: number; c: number; w: number } | { tipo: 'secao'; s: number } | { tipo: 'novo'; t: Tipo } | null

export function EditorDePagina({ id }: { id: number }) {
  const { can } = useAuth()
  const gerente = can('MANAGER')
  const toast = useToast()
  const l = useGet<Saida>(`/site/editor/paginas/${id}`)
  const [c, setC] = useState<Conteudo | null>(null)
  const [seo, setSeo] = useState<{ title: string; description: string; path: string } | null>(null)
  const [sujo, setSujo] = useState(false)
  const [saida, setSaida] = useState<Saida | null>(null)
  const [aberto, setAberto] = useState<string | null>(null)
  const [arrasto, setArrasto] = useState<Arrasto>(null)
  const [vista, setVista] = useState<'estrutura' | 'previa'>('estrutura')
  const [tela, setTela] = useState<'celular' | 'computador'>('celular')
  const [v, setV] = useState(0)
  const [versoes, setVersoes] = useState<{ id: number; title: string; published_at: string; por: string | null }[] | null>(null)
  const novaFoto = useRef<{ s: number; c: number } | null>(null)
  const arquivo = useRef<HTMLInputElement>(null)
  const atual = saida || l.data
  // o que chegou do servidor vira o estado local uma vez (depois, é o editor que manda)
  if (l.data && !c) { setC(l.data.pagina.draft); setSeo({ title: l.data.pagina.title, description: l.data.pagina.description, path: l.data.pagina.path }) }
  useEffect(() => {
    if (!sujo || !c || !seo || !gerente) return
    const t = setTimeout(async () => {
      try {
        const r = await api.patch<Saida>(`/site/editor/paginas/${id}`, { conteudo: c, title: seo.title, description: seo.description,
          ...(atual && !atual.pagina.base && !atual.pagina.published ? { path: seo.path } : {}) })
        setSaida(r); setSujo(false); setV(n => n + 1)
      } catch (er) { toast((er as ApiError).message, 'crit'); setSujo(false) }
    }, 700)
    return () => clearTimeout(t)
  }, [sujo, c, seo, id, gerente, atual, toast])
  if (l.error && !l.data) return <ErrorState error={l.error} retry={l.reload} />
  if (!atual || !c || !seo) return <Loading />
  const p = atual.pagina
  const mudar = (n: Conteudo) => { setC(n); setSujo(true) }
  const itens = c.itens
  const comItens = (f: (xs: Item[]) => Item[]) => mudar({ itens: f(itens.map(x => x.tipo === 'secao' ? { ...x, itens: x.itens.map(col => [...col]) } : { ...x })) })
  const secao = (xs: Item[], s: number) => xs[s] as Secao
  const moverItem = (s: number, passo: number) => comItens(xs => { const t = s + passo; if (t < 0 || t >= xs.length) return xs; const [x] = xs.splice(s, 1); xs.splice(t, 0, x); return xs })
  const mudaSecao = (s: number, x: Partial<Secao>) => comItens(xs => { const sc = { ...secao(xs, s), ...x }
    if (x.colunas) { const cols = [...sc.itens]; while (cols.length < x.colunas) cols.push([]); while (cols.length > x.colunas) { const ult = cols.pop() || []; cols[cols.length - 1] = [...cols[cols.length - 1], ...ult] } sc.itens = cols }
    xs[s] = sc; return xs })
  const mudaWidget = (s: number, col: number, i: number, x: Partial<W>) => comItens(xs => { const sc = secao(xs, s); sc.itens[col][i] = { ...sc.itens[col][i], ...x }; return xs })
  const tirarWidget = (s: number, col: number, i: number) => comItens(xs => { secao(xs, s).itens[col].splice(i, 1); return xs })
  const porWidget = (s: number, col: number, i: number, w: W) => comItens(xs => { secao(xs, s).itens[col].splice(i, 0, w); return xs })
  function moverWidget(s: number, col: number, i: number, passo: number) {
    comItens(xs => {
      const lista = secao(xs, s).itens[col]
      const [w] = lista.splice(i, 1)
      const t = i + passo
      if (t >= 0 && t <= lista.length) { lista.splice(t, 0, w); return xs }
      // no começo ou no fim da coluna: passa para a seção de cima ou de baixo
      for (let k = s + passo; k >= 0 && k < xs.length; k += passo) {
        const o = xs[k]
        if (o.tipo === 'secao') { const alvo = passo < 0 ? o.itens[o.itens.length - 1] : o.itens[0]; if (passo < 0) alvo.push(w); else alvo.unshift(w); return xs }
      }
      lista.splice(i, 0, w); return xs
    })
  }
  function soltar(destS: number, destC: number, destI: number) {
    const a = arrasto; setArrasto(null)
    if (!a) return
    if (a.tipo === 'novo') {
      if (a.t === 'imagem') { novaFoto.current = { s: destS, c: destC }; arquivo.current?.click(); return }
      const w = novoWidget(a.t); porWidget(destS, destC, destI, w); setAberto(w.id); return
    }
    if (a.tipo !== 'widget') return
    comItens(xs => {
      const [w] = secao(xs, a.s).itens[a.c].splice(a.w, 1)
      const ajuste = a.s === destS && a.c === destC && a.w < destI ? 1 : 0
      secao(xs, destS).itens[destC].splice(destI - ajuste, 0, w); return xs
    })
  }
  function soltarSecao(dest: number) {
    const a = arrasto; setArrasto(null)
    if (!a || a.tipo !== 'secao' || a.s === dest) return
    comItens(xs => { const [x] = xs.splice(a.s, 1); xs.splice(a.s < dest ? dest - 1 : dest, 0, x); return xs })
  }
  async function subirFoto(f: File | undefined) {
    const alvo = novaFoto.current; novaFoto.current = null
    if (!f || !alvo) return
    try { const fd = new FormData(); fd.append('arquivo', f)
      const r = await api.postForm<{ src: string; largura: number; altura: number }>('/site/editor/fotos', fd)
      const w: W = { id: novoId(), tipo: 'imagem', src: r.src, largura: r.largura, altura: r.altura, alt: '', forma: 'larga', legenda: '' }
      porWidget(alvo.s, alvo.c, secao(itens, alvo.s).itens[alvo.c].length, w); setAberto(w.id); toast(tr("Foto salva: escreva a descrição dela."), 'ok') }
    catch (er) { toast((er as ApiError).message, 'crit') }
  }
  function adicionar(s: number, col: number, t: Tipo) {
    if (t === 'imagem') { novaFoto.current = { s, c: col }; arquivo.current?.click(); return }
    const w = novoWidget(t); porWidget(s, col, secao(itens, s).itens[col].length, w); setAberto(w.id)
  }
  async function acao(caminho: string, ok: string) {
    try { const r = await api.post<Saida>(`/site/editor/paginas/${id}/${caminho}`); setSaida(r); setV(n => n + 1); toast(ok, 'ok'); if (versoes) abrirVersoes() }
    catch (er) { toast((er as ApiError).message, 'crit') }
  }
  async function abrirVersoes() {
    try { setVersoes((await api.get<{ versoes: { id: number; title: string; published_at: string; por: string | null }[] }>(`/site/editor/paginas/${id}/versoes`)).versoes) }
    catch (er) { toast((er as ApiError).message, 'crit') }
  }
  async function voltarVersao(vid: number) {
    try { const r = await api.post<Saida>(`/site/editor/paginas/${id}/versoes/${vid}/voltar`); setSaida(r); setC(r.pagina.draft)
      setSeo({ title: r.pagina.title, description: r.pagina.description, path: r.pagina.path }); setV(n => n + 1)
      toast(tr("A versão voltou para o rascunho: confira e publique."), 'ok') }
    catch (er) { toast((er as ApiError).message, 'crit') }
  }
  const podeArrastar = gerente
  const entreSecoes = (k: number) => gerente && <div className={`ed-solta-secao${arrasto?.tipo === 'secao' ? ' on' : ''}`}
    onDragOver={e => { if (arrasto?.tipo === 'secao') e.preventDefault() }} onDrop={e => { e.preventDefault(); soltarSecao(k) }}>
    <button className="btn sm ghost" onClick={() => comItens(xs => { xs.splice(k, 0, novaSecao()); return xs })}>{tr("+ Seção aqui")}</button></div>

  return <div className="stack" style={{ gap: 12 }}>
    <input ref={arquivo} type="file" accept="image/*" className="sr-only" tabIndex={-1} aria-hidden="true" onChange={e => { subirFoto(e.target.files?.[0]); e.target.value = '' }} />
    <div className="row wrap" style={{ gap: 8 }}>
      <Link className="btn sm ghost" to="/site/editor">{tr("← Páginas")}</Link>
      <div className="grow" />
      <Chip tone={ESTADO[p.estado][1]}>{ESTADO[p.estado][0]}</Chip>
      {sujo && <span className="small muted">{tr("salvando…")}</span>}
      {p.published && <a className="btn sm ghost" href={p.path} target="_blank" rel="noreferrer">{tr("Ver no site ↗")}</a>}
    </div>
    <section className="card"><div className="card-h"><h2 className="h2" style={{ overflowWrap: 'anywhere' }}>{seo.title || p.path}</h2></div>
      <div className="card-b stack" style={{ gap: 10 }}>
        <div className="loja-grade">
          <label className="fld"><span>{tr("Título da aba")} <i>{tr("10 a 70 letras; o Google mostra")}</i></span><input value={seo.title} disabled={!gerente} onChange={e => { setSeo({ ...seo, title: e.target.value }); setSujo(true) }} /></label>
          <label className="fld"><span>{tr("Endereço")}</span><input value={seo.path} disabled={!gerente || !!p.base || !!p.published} onChange={e => { setSeo({ ...seo, path: e.target.value }); setSujo(true) }} /></label>
          <label className="fld" style={{ gridColumn: '1 / -1' }}><span>{tr("Descrição")} <i>{tr("50 a 170 letras; o texto do Google embaixo do título")}</i></span>
            <textarea rows={2} value={seo.description} disabled={!gerente} onChange={e => { setSeo({ ...seo, description: e.target.value }); setSujo(true) }} /></label>
        </div>
        {atual.problemas.length > 0 && <div className="ed-problemas" role="status"><b>{tr("Antes de publicar:")}</b><ul>{atual.problemas.map(x => <li key={x}>{x}</li>)}</ul></div>}
        {gerente && <div className="row wrap" style={{ gap: 8 }}>
          <button className="btn primary" disabled={sujo || atual.problemas.length > 0} onClick={() => acao('publicar', tr("Publicado: o site já mostra."))}>{tr("Publicar")}</button>
          {p.published && <button className="btn ghost" onClick={() => acao('despublicar', p.base ? tr("O site voltou à página original.") : tr("A página saiu do ar."))}>{p.base ? tr("Voltar ao original") : tr("Tirar do ar")}</button>}
          <button className="btn ghost" onClick={() => versoes ? setVersoes(null) : abrirVersoes()}>{versoes ? tr("Fechar versões") : tr("Versões")}</button>
        </div>}
        {versoes && <div className="stack" style={{ gap: 6 }}><h3 className="h3" style={{ margin: 0 }}>{tr("Versões publicadas")}</h3>
          {!versoes.length ? <p className="small muted" style={{ margin: 0 }}>{tr("Ainda não foi publicada.")}</p>
            : versoes.map(x => <div key={x.id} className="row wrap" style={{ gap: 8 }}><span className="small grow">{fmtDateTime(x.published_at)} · {x.por || '—'} · {x.title}</span>
              {gerente && <button className="btn sm ghost" onClick={() => voltarVersao(x.id)}>{tr("Voltar a esta versão")}</button>}</div>)}</div>}
      </div>
    </section>

    <div className="seg ed-vista" role="group" aria-label={tr("O que mostrar")}>
      <button className={`btn sm${vista === 'estrutura' ? '' : ' ghost'}`} aria-pressed={vista === 'estrutura'} onClick={() => setVista('estrutura')}>{tr("Montar")}</button>
      <button className={`btn sm${vista === 'previa' ? '' : ' ghost'}`} aria-pressed={vista === 'previa'} onClick={() => setVista('previa')}>{tr("Ver como fica")}</button>
    </div>
    <div className={`ed-painel ed-mostra-${vista}`}>
      <div className="ed-estrutura stack" style={{ gap: 8 }}>
        {gerente && <div className="card card-b ed-paleta-card"><div className="small muted" style={{ marginBottom: 6 }}>{tr("Arraste um elemento para uma coluna (ou use o + Elemento da coluna):")}</div>
          <div className="row wrap" style={{ gap: 6 }}>{PALETA.map(t => <button key={t} className="btn sm ghost ed-paleta" draggable={podeArrastar}
            onDragStart={e => { marcar(e, t); setArrasto({ tipo: 'novo', t }) }} onDragEnd={() => setArrasto(null)} onClick={() => { const s = itens.findIndex(x => x.tipo === 'secao'); if (s >= 0) adicionar(s, 0, t); else toast(tr("Crie uma seção primeiro."), 'warn') }}>{NOMES[t]}</button>)}</div></div>}
        {itens.map((it, s) => <div key={it.id}>
          {entreSecoes(s)}
          {it.tipo === 'original'
            ? <div className={`card card-b ed-item ed-original${it.oculto ? ' oculto' : ''}`} draggable={podeArrastar} onDragStart={e => { marcar(e, 'secao'); setArrasto({ tipo: 'secao', s }) }} onDragEnd={() => setArrasto(null)}>
              <div className="row wrap" style={{ gap: 6 }}>
                <span className="grow small" style={{ minWidth: 0, overflowWrap: 'anywhere' }}><b>{tr("Faixa original {0}", it.indice + 1)}</b>{atual.originais[it.indice] ? ` · ${atual.originais[it.indice]}` : ''}{it.oculto ? ` · ${tr("escondida")}` : ''}</span>
                {gerente && <>
                  <button className="btn sm ghost" aria-label={tr("Subir")} disabled={s === 0} onClick={() => moverItem(s, -1)}>↑</button>
                  <button className="btn sm ghost" aria-label={tr("Descer")} disabled={s === itens.length - 1} onClick={() => moverItem(s, 1)}>↓</button>
                  <button className="btn sm ghost" onClick={() => comItens(xs => { xs[s] = { ...(xs[s] as Original), oculto: !it.oculto }; return xs })}>{it.oculto ? tr("Mostrar") : tr("Esconder")}</button></>}
              </div></div>
            : <div className="card ed-item ed-secao-card" data-secao={it.id}>
              <div className="card-h row wrap" style={{ gap: 6 }} draggable={podeArrastar} onDragStart={e => { marcar(e, 'secao'); setArrasto({ tipo: 'secao', s }) }} onDragEnd={() => setArrasto(null)}>
                <h3 className="h3 grow" style={{ margin: 0 }}>{tr("Seção")} {s + 1}</h3>
                {gerente && <>
                  <button className="btn sm ghost" aria-label={tr("Subir")} disabled={s === 0} onClick={() => moverItem(s, -1)}>↑</button>
                  <button className="btn sm ghost" aria-label={tr("Descer")} disabled={s === itens.length - 1} onClick={() => moverItem(s, 1)}>↓</button>
                  <button className="btn sm ghost" onClick={() => comItens(xs => { const o = xs[s] as Secao; xs.splice(s + 1, 0, { ...o, id: novoId(), itens: o.itens.map(col => col.map(w => ({ ...w, id: novoId() }))) }); return xs })}>{tr("Duplicar")}</button>
                  <button className="btn sm ghost" onClick={() => comItens(xs => { xs.splice(s, 1); return xs })}>{tr("Apagar")}</button></>}
              </div>
              <div className="card-b stack" style={{ gap: 8 }}>
                <div className="loja-grade ed-secao-opcoes">
                  <Opcoes rotulo={tr("Fundo")} valor={it.fundo} opcoes={FUNDOS} disabled={!gerente} onChange={x => mudaSecao(s, { fundo: x })} />
                  <Opcoes rotulo={tr("Espaçamento")} valor={it.espaco} opcoes={TAM} disabled={!gerente} onChange={x => mudaSecao(s, { espaco: x })} />
                  <Opcoes rotulo={tr("Colunas")} valor={String(it.colunas)} opcoes={[['1', '1'], ['2', '2'], ['3', '3']]} disabled={!gerente} onChange={x => mudaSecao(s, { colunas: Number(x) })} />
                </div>
                <div className={`ed-colunas ed-colunas-${it.colunas}`}>{it.itens.map((col, ci) => <div key={ci} className={`ed-coluna${arrasto && arrasto.tipo !== 'secao' ? ' on' : ''}`}
                  onDragOver={e => { if (arrasto && arrasto.tipo !== 'secao') e.preventDefault() }} onDrop={e => { e.preventDefault(); soltar(s, ci, col.length) }}>
                  {it.colunas > 1 && <div className="small muted">{tr("Coluna {0}", ci + 1)}</div>}
                  {col.map((w, wi) => <div key={w.id} className={`ed-widget${aberto === w.id ? ' aberto' : ''}`} data-widget={w.tipo} draggable={podeArrastar && aberto !== w.id}
                    onDragStart={e => { e.stopPropagation(); marcar(e, w.id); setArrasto({ tipo: 'widget', s, c: ci, w: wi }) }} onDragEnd={() => setArrasto(null)}
                    onDragOver={e => { if (arrasto && arrasto.tipo !== 'secao') { e.preventDefault(); e.stopPropagation() } }} onDrop={e => { e.preventDefault(); e.stopPropagation(); soltar(s, ci, wi) }}>
                    <div className="row" style={{ gap: 6 }}>
                      <button className="ed-widget-nome grow" aria-expanded={aberto === w.id} onClick={() => setAberto(aberto === w.id ? null : w.id)}>
                        <b>{NOMES[w.tipo]}</b> <span className="small muted">{resumo(w)}</span></button>
                      {gerente && <>
                        <button className="btn sm ghost" aria-label={tr("Subir")} onClick={() => moverWidget(s, ci, wi, -1)}>↑</button>
                        <button className="btn sm ghost" aria-label={tr("Descer")} onClick={() => moverWidget(s, ci, wi, 1)}>↓</button></>}
                    </div>
                    {aberto === w.id && <div className="stack" style={{ gap: 8, marginTop: 8 }}>
                      <FormWidget w={w} gerente={gerente} muda={x => mudaWidget(s, ci, wi, x)} />
                      {gerente && <div className="row wrap" style={{ gap: 6 }}>
                        {it.colunas > 1 && ci > 0 && <button className="btn sm ghost" onClick={() => comItens(xs => { const sc = secao(xs, s); const [x] = sc.itens[ci].splice(wi, 1); sc.itens[ci - 1].push(x); return xs })}>{tr("← Coluna")}</button>}
                        {it.colunas > 1 && ci < it.colunas - 1 && <button className="btn sm ghost" onClick={() => comItens(xs => { const sc = secao(xs, s); const [x] = sc.itens[ci].splice(wi, 1); sc.itens[ci + 1].push(x); return xs })}>{tr("Coluna →")}</button>}
                        <button className="btn sm ghost" onClick={() => porWidget(s, ci, wi + 1, { ...w, id: novoId() })}>{tr("Duplicar")}</button>
                        <button className="btn sm ghost" onClick={() => tirarWidget(s, ci, wi)}>{tr("Apagar")}</button></div>}
                    </div>}
                  </div>)}
                  {gerente && <details className="ed-mais"><summary className="btn sm ghost">{tr("+ Elemento")}</summary>
                    <div className="row wrap" style={{ gap: 6, marginTop: 6 }}>{PALETA.map(t => <button key={t} className="btn sm ghost" onClick={e => { adicionar(s, ci, t); (e.currentTarget.closest('details') as HTMLDetailsElement).open = false }}>{NOMES[t]}</button>)}</div></details>}
                </div>)}</div>
              </div>
            </div>}
        </div>)}
        {entreSecoes(itens.length)}
      </div>
      <div className="ed-previa">
        <div className="seg" role="group" aria-label={tr("Tamanho da pré-visualização")} style={{ marginBottom: 8 }}>
          <button className={`btn sm${tela === 'celular' ? '' : ' ghost'}`} aria-pressed={tela === 'celular'} onClick={() => setTela('celular')}>{tr("Celular")}</button>
          <button className={`btn sm${tela === 'computador' ? '' : ' ghost'}`} aria-pressed={tela === 'computador'} onClick={() => setTela('computador')}>{tr("Computador")}</button>
        </div>
        <iframe key={v} className={`ed-iframe ed-iframe-${tela}`} title={tr("Pré-visualização da página")} src={`${atual.previa}?v=${v}`} />
      </div>
    </div>
  </div>
}
