/* Editor do site como o Canva (#315). Dono, 16/10: "o editor do site ele abre uma mini visualização de como é o site
 * público. E dali a pessoa consegue, por ali, clicar no que ela precisa editar. Ela edita, ela puxa, ela arrasta, ela
 * solta, ela insere alguma coisa com o mouse, por exemplo, usando o mouse e teclado, sem precisar de preencher cards
 * para aquilo ali. ... É como se fosse um Canva."
 *
 * A prévia é a área de trabalho (Lona): clique seleciona, clique de novo (ou duplo, ou Enter) escreve no lugar, a
 * barra em cima da peça muda o resto, arrastar move, a paleta põe peças novas e as Camadas fazem o mesmo com botões.
 * O rascunho salva sozinho (com a revisão: duas pessoas não apagam o que a outra fez) e a prévia troca só a seção que
 * mudou, sem recarregar. Publicar só com tudo salvo, sem erro e sem pendência: o que vai para o ar é o que a tela
 * mostra. */
import { useEffect, useRef, useState, type PointerEvent as PE } from 'react'
import { createPortal } from 'react-dom'
import { Link } from 'react-router-dom'
import { api, ApiError } from '../../api/client'
import { useGet } from '../../api/hooks'
import { useAuth } from '../../auth/AuthContext'
import { Chip, ErrorState, Loading } from '../../components/ui'
import { Icon } from '../../components/Icon'
import { useToast } from '../../components/Toast'
import { tr } from '../../i18n'
import { Barra, type AcoesBarra, type Ancora } from './Barra'
import { Camadas } from './Camadas'
import { Historico } from './historico'
import { Lona, type LonaApi } from './Lona'
import { acharS, acharW, alternarOculto, colunaW, DE_ESCREVER, duplicarS, duplicarW, existe, item, moverS, moverW, mudarS, mudarW,
  NOMES, nomeDaPeca, nomeDe, novaSecao, novoWidget, ondeEsta, ordem, passoS, passoW, porSecao, porW, secaoDe, tirarS, tirarW, widget,
  type Peca } from './modelo'
import { PaginaPainel, type Versao } from './PaginaPainel'
import { Paleta } from './Paleta'
import type { Ganchos, Ponte } from './ponte'
import type { Conteudo, Destino, Doc, Saida, Secao, Sel, Seo, Tipo, W } from './tipos'

const ESTADO: Record<string, [string, 'neutral' | 'ok' | 'warn']> = {
  rascunho: [tr("rascunho, fora do ar"), 'neutral'], publicada: [tr("no ar"), 'ok'], mudou: [tr("no ar, com mudanças não publicadas"), 'warn'] }
type Aba = 'inserir' | 'camadas' | 'pagina'
const ABAS: [Aba, string][] = [['inserir', tr("Inserir")], ['camadas', tr("Camadas")], ['pagina', tr("Página")]]

const DICAS: Record<string, string> = { titulo: tr("Escreva o título"), texto: tr("Escreva aqui"), botao: tr("Texto do botão"),
  lista: tr("Escreva um item"), item: tr("Escreva um item"), pergunta: tr("A pergunta"), resposta: tr("A resposta"),
  imagem: tr("Solte uma foto aqui ou use Escolher foto"), faq: tr("Perguntas frequentes: use + Pergunta"),
  karts: tr("Sem karts para mostrar (vêm de Serviços e preços)"), produtos: tr("Nenhum produto em estoque nessa categoria (Produtos da loja)"),
  cartoes: tr("Sem cartões nessa página (Cartões das páginas)"), espaco: '' }
const dica = (t: string) => DICAS[t] ?? ''

/** Tela estreita (celular): a lona na largura toda, a barra embaixo e as folhas de Inserir, Camadas e Página. */
function useEstreito() {
  const q = '(max-width: 900px)'
  const [v, setV] = useState(() => window.matchMedia(q).matches)
  useEffect(() => {
    const m = window.matchMedia(q)
    const f = () => setV(m.matches)
    m.addEventListener('change', f)
    return () => m.removeEventListener('change', f)
  }, [])
  return v
}
/** A altura do teclado do celular (a barra de baixo sobe junto). */
function useTeclado() {
  const [h, setH] = useState(0)
  useEffect(() => {
    const vv = window.visualViewport
    if (!vv) return
    const f = () => setH(Math.max(0, Math.round(window.innerHeight - vv.height - vv.offsetTop)))
    vv.addEventListener('resize', f); vv.addEventListener('scroll', f)
    return () => { vv.removeEventListener('resize', f); vv.removeEventListener('scroll', f) }
  }, [])
  return h
}

export function EditorDePagina({ id }: { id: number }) {
  const { can } = useAuth()
  const gerente = can('MANAGER')
  const toast = useToast()
  const l = useGet<Saida>(`/site/editor/paginas/${id}`)
  const estreito = useEstreito()
  const teclado = useTeclado()

  const [doc, setDoc] = useState<Doc | null>(null)
  const [saida, setSaida] = useState<Saida | null>(null)
  const [erros, setErros] = useState<Record<string, string>>({})
  const [sel, setSel] = useState<Sel>(null)
  const [editando, setEditando] = useState<string | null>(null)
  const [aba, setAba] = useState<Aba>('inserir')
  const [folha, setFolha] = useState<Aba | null>(null)
  const [tela, setTela] = useState<'celular' | 'computador'>('celular')
  const [salvo, setSalvo] = useState<'salvo' | 'salvando' | 'erro' | 'conflito'>('salvo')
  const [erroSalvar, setErroSalvar] = useState('')
  const [ancora, setAncora] = useState<Ancora | null>(null)
  const [limites, setLimites] = useState({ w: 0, h: 0 })
  const [tampa, setTampa] = useState(false)
  const [fantasma, setFantasma] = useState<{ nome: string; x: number; y: number } | null>(null)
  const [porTocar, setPorTocar] = useState<Peca | null>(null)
  const [aviso, setAviso] = useState('')
  const [versoes, setVersoes] = useState<Versao[] | null>(null)
  const [balao, setBalao] = useState<{ qual: 'link' | 'alt' | 'linkTexto'; vez: number } | null>(null)
  const [, setVez] = useState(0)

  const docRef = useRef<Doc | null>(null)
  const saidaRef = useRef<Saida | null>(null)
  const selRef = useRef<Sel>(null)
  const editRef = useRef<string | null>(null)
  const errosRef = useRef<Record<string, string>>({})
  const hist = useRef(new Historico<Doc>())
  const lona = useRef<LonaApi>(null)
  const arquivo = useRef<HTMLInputElement>(null)
  const fotoPara = useRef<Destino | { tipo: 'troca'; id: string } | null>(null)
  const editarDepois = useRef<string | null>(null)
  const mudouNoTexto = useRef(false)
  const engolirClique = useRef(false)
  const quadro = useRef(0)
  // o salvar: uma requisição por vez, sempre com a revisão que a tela tem
  const rev = useRef(0)
  const versaoLocal = useRef(0)
  const versaoSalva = useRef(0)
  const emVoo = useRef(false)
  const pendente = useRef(false)
  const pedeDesenhar = useRef(false)
  const timer = useRef(0)
  const parado = useRef(false)

  const ponte = (): Ponte | null => lona.current?.ponte() || null

  useEffect(() => {
    if (!l.data || docRef.current) return
    const d: Doc = { c: l.data.pagina.draft, seo: { title: l.data.pagina.title, description: l.data.pagina.description, path: l.data.pagina.path } }
    docRef.current = d; setDoc(d)
    saidaRef.current = l.data; setSaida(l.data)
    rev.current = l.data.pagina.rev || 0
  }, [l.data])
  // saiu da tela (← Páginas, outra aba do menu) com mudança ainda no relógio do salvar: manda já
  const enviarJa = useRef<() => void>(() => {})
  useEffect(() => () => {
    cancelAnimationFrame(quadro.current)
    if (versaoLocal.current !== versaoSalva.current) enviarJa.current()
    window.clearTimeout(timer.current)
  }, [])
  // um arquivo solto fora da prévia não abre no lugar do painel
  useEffect(() => {
    const f = (e: DragEvent) => { if (Array.from(e.dataTransfer?.types || []).includes('Files')) e.preventDefault() }
    window.addEventListener('dragover', f); window.addEventListener('drop', f)
    return () => { window.removeEventListener('dragover', f); window.removeEventListener('drop', f) }
  }, [])
  // sair com mudança não salva: o navegador pergunta
  useEffect(() => {
    const f = (e: BeforeUnloadEvent) => { if (versaoLocal.current !== versaoSalva.current) e.preventDefault() }
    window.addEventListener('beforeunload', f)
    return () => window.removeEventListener('beforeunload', f)
  }, [])

  // ------------------------------------------------------------------ salvar
  async function enviar() {
    window.clearTimeout(timer.current)
    const d = docRef.current
    if (parado.current || !d || !gerente) return
    if (emVoo.current) { pendente.current = true; return }
    emVoo.current = true
    const versao = versaoLocal.current
    const desenhar = pedeDesenhar.current
    pedeDesenhar.current = false
    const p = saidaRef.current?.pagina
    let falhou = false
    try {
      const r = await api.patch<Saida>(`/site/editor/paginas/${id}`, { conteudo: d.c, title: d.seo.title, description: d.seo.description,
        ...(p && !p.base && !p.published ? { path: d.seo.path } : {}), rev: rev.current, desenhar })
      rev.current = r.pagina.rev
      versaoSalva.current = versao
      saidaRef.current = r; setSaida(r)
      errosRef.current = r.erros || {}; setErros(errosRef.current)
      setErroSalvar('')
      const pt = ponte()
      if (r.secoes && pt) {
        if (versaoLocal.current === versao) {
          pt.aplicarSecoes(r.secoes)
          const ed = editarDepois.current
          if (ed) { editarDepois.current = null; if (selRef.current?.id === ed) editarTexto(ed, undefined, true) }
        } else pedeDesenhar.current = true
      }
      pt?.marcarErros(Object.keys(errosRef.current))
      reposicionar()
    } catch (er) {
      const e = er as ApiError
      falhou = true
      pedeDesenhar.current = pedeDesenhar.current || desenhar
      if (e.status === 409) { parado.current = true; setSalvo('conflito'); setErroSalvar(e.message) }
      else { setSalvo('erro'); setErroSalvar(e.message) }
    } finally {
      emVoo.current = false
      if (!parado.current) {
        if (!falhou && (pendente.current || versaoLocal.current !== versaoSalva.current)) { pendente.current = false; timer.current = window.setTimeout(enviar, 200) }
        else if (!falhou) setSalvo('salvo')
      }
    }
  }
  enviarJa.current = enviar
  function agendar(desenhar: boolean, atraso: number) {
    if (desenhar) pedeDesenhar.current = true
    if (parado.current) return
    setSalvo('salvando')
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(enviar, atraso)
  }
  /** Aplica uma mudança: guarda o antes no desfazer, mostra na hora e salva (`chave`: a digitação seguida junta). */
  function mudar(fn: (d: Doc) => Doc, o: { chave?: string; desenhar?: boolean; anuncio?: string } = {}) {
    const atual = docRef.current
    if (!atual || !gerente) return null
    const novo = fn(atual)
    if (novo === atual) return null
    hist.current.registrar(atual, o.chave)
    definir(novo)
    agendar(o.desenhar !== false, o.chave ? 700 : 220)
    if (o.anuncio) setAviso(o.anuncio)
    setVez(x => x + 1)
    return novo
  }
  function definir(novo: Doc) {
    docRef.current = novo
    setDoc(novo)
    versaoLocal.current++
    ponte()?.sincronizar(novo.c)
  }
  const mudarC = (fn: (c: Conteudo) => Conteudo, o?: { chave?: string; desenhar?: boolean; anuncio?: string }) =>
    mudar(d => { const c = fn(d.c); return c === d.c ? d : { ...d, c } }, o)?.c || null
  const mudarSeo = (x: Partial<Seo>) => mudar(d => ({ ...d, seo: { ...d.seo, ...x } }), { chave: `seo:${Object.keys(x).join()}`, desenhar: false })

  function desfazer(volta = true) {
    const atual = docRef.current
    if (!atual) return
    ponte()?.pararEdicao()
    const x = volta ? hist.current.desfazer(atual) : hist.current.refazer(atual)
    if (!x) return
    definir(x)
    agendar(true, 0)
    if (!existe(x.c, selRef.current)) selecionar(null)
    setAviso(volta ? tr("Desfeito") : tr("Refeito"))
    setVez(n => n + 1)
  }

  // ------------------------------------------------------------------ seleção e texto
  function reposicionar() {
    cancelAnimationFrame(quadro.current)
    quadro.current = requestAnimationFrame(() => {
      const s = selRef.current
      const pt = ponte()
      const r = s && pt ? pt.retangulo(s) : null
      setAncora(r ? lona.current?.paraFora(r) || null : null)
      const t = lona.current?.tamanho()
      if (t) setLimites(o => o.w === t.w && o.h === t.h ? o : t)
    })
  }
  function selecionar(s: Sel, rolar = false) {
    if (editRef.current && (!s || s.id !== editRef.current)) ponte()?.pararEdicao()
    selRef.current = s
    setSel(s)
    ponte()?.marcar(s)
    if (rolar) ponte()?.rolarAte(s)
    hist.current.cortar()
    reposicionar()
  }
  function editarTexto(wid: string, ponto?: { x: number; y: number }, tudo = false) {
    const w = docRef.current && widget(docRef.current.c, wid)
    if (!w || !gerente || !DE_ESCREVER.includes(w.tipo)) return
    if (ponte()?.editarTexto(wid, ponto, tudo)) { editRef.current = wid; setEditando(wid); mudouNoTexto.current = false }
  }

  const ganchos = useRef<Ganchos | null>(null)
  ganchos.current = {
    clique(s, ev) {
      if (porTocar) {
        const d = ponte()?.destinoDoToque(ev.x, ev.y)
        const p = porTocar
        setPorTocar(null)
        if (d) inserir(p, d)
        return
      }
      const ja = !!s && selRef.current?.tipo === s.tipo && selRef.current.id === s.id
      selecionar(s)
      if (s?.tipo === 'w' && (ev.duplo || ja)) editarTexto(s.id, { x: ev.x, y: ev.y })
    },
    digitou(wid, valor) { mudouNoTexto.current = true; mudarC(c => mudarW(c, wid, valor), { chave: `tx:${wid}`, desenhar: false }) },
    saiuDaEdicao() {
      editRef.current = null
      setEditando(null)
      hist.current.cortar()
      // o que mudou enquanto escrevia (o texto, ou o nível e a cor pela barra) volta desenhado pelo servidor
      if (mudouNoTexto.current || ponte()?.temPulada) { mudouNoTexto.current = false; agendar(true, 150) }
      reposicionar()
    },
    tecla(e) { teclar(e) },
    arrastou(oQue, d) {
      if (oQue.tipo === 's' && typeof d === 'number') {
        const c1 = mudarC(c => moverS(c, oQue.id, d))
        if (c1) setAviso(tr("{0} movida", nomeDe(c1, oQue, saidaRef.current?.originais || [])))
        selecionar(oQue)
      } else if (oQue.tipo === 'w' && typeof d === 'object') {
        const c1 = mudarC(c => moverW(c, oQue.id, d))
        if (c1) { refletir(c1, oQue.id); setAviso(tr("{0} movido para {1}", NOMES[widget(c1, oQue.id)?.tipo || 'titulo'], ondeEsta(c1, oQue.id))) }
        selecionar(oQue)
      }
    },
    arquivo(f, d) { subirFoto(f, d) },
    mudouVista() { reposicionar() },
  }
  const pegarGanchos = () => ganchos.current as Ganchos

  /** O nó do elemento vai na hora para onde o modelo diz (o servidor confirma depois). */
  function refletir(c: Conteudo, wid: string) {
    const lg = acharW(c, wid)
    if (lg) ponte()?.moverNo(wid, c.itens[lg.s].id, lg.c, lg.i)
  }

  // ------------------------------------------------------------------ as ações
  function destinoDaSelecao(c: Conteudo): Destino {
    const s = selRef.current
    if (s?.tipo === 'w') { const lg = acharW(c, s.id); if (lg) return { tipo: 'col', sid: c.itens[lg.s].id, c: lg.c, i: lg.i + 1 } }
    if (s?.tipo === 's') {
      const it = item(c, s.id)
      if (it?.tipo === 'secao') return { tipo: 'col', sid: it.id, c: 0, i: it.itens[0].length }
      if (it) return { tipo: 'nova', i: acharS(c, s.id) + 1 }
    }
    const ult = [...c.itens].reverse().find((x): x is Secao => x.tipo === 'secao')
    return ult ? { tipo: 'col', sid: ult.id, c: 0, i: ult.itens[0].length } : { tipo: 'nova', i: c.itens.length }
  }
  function inserir(p: Peca, d: Destino | null) {
    const c0 = docRef.current?.c
    if (!c0 || !gerente) return
    if (p.startsWith('secao')) {
      const sc = novaSecao(Number(p.slice(5)))
      const alvo = d || destinoDaSelecao(c0)
      const i = alvo.tipo === 'nova' ? alvo.i : acharS(c0, alvo.sid) + 1
      if (mudarC(c => porSecao(c, sc, i), { anuncio: tr("{0} inserida", nomeDaPeca(p)) })) selecionar({ tipo: 's', id: sc.id }, true)
      return
    }
    const w = novoWidget(p as Tipo)
    const alvo = d || destinoDaSelecao(c0)
    const c1 = mudarC(c => porW(c, w, alvo))
    if (!c1) return
    setAviso(tr("{0} inserido em {1}", NOMES[w.tipo], ondeEsta(c1, w.id)))
    selecionar({ tipo: 'w', id: w.id })
    if (w.tipo === 'imagem') { fotoPara.current = { tipo: 'troca', id: w.id }; arquivo.current?.click() }
    else if (DE_ESCREVER.includes(w.tipo)) editarDepois.current = w.id
  }
  async function subirFoto(f: File, d: Destino | { tipo: 'troca'; id: string }) {
    if (!gerente) return
    try {
      const fd = new FormData()
      fd.append('arquivo', f)
      const r = await api.postForm<{ src: string; largura: number; altura: number }>('/site/editor/fotos', fd)
      const foto = { src: r.src, largura: r.largura, altura: r.altura }
      let wid: string
      if (d.tipo === 'troca') { wid = d.id; mudarC(c => mudarW(c, d.id, foto)) }
      else {
        const w: W = { ...novoWidget('imagem'), ...foto }
        wid = w.id
        mudarC(c => porW(c, w, d))
      }
      selecionar({ tipo: 'w', id: wid })
      if (!docRef.current || !widget(docRef.current.c, wid)?.alt) setBalao({ qual: 'alt', vez: Date.now() })
      toast(tr("Foto salva (WebP, sem a localização do celular): escreva a descrição dela."), 'ok')
    } catch (er) { toast((er as ApiError).message, 'crit') }
  }
  function mover(s: NonNullable<Sel>, passo: number) {
    const c0 = docRef.current?.c
    if (!c0) return
    if (s.tipo === 'w') {
      const c1 = mudarC(c => passoW(c, s.id, passo))
      if (c1) { refletir(c1, s.id); setAviso(tr("{0} movido para {1}", NOMES[widget(c1, s.id)?.tipo || 'titulo'], ondeEsta(c1, s.id))) }
    } else {
      const c1 = mudarC(c => passoS(c, s.id, passo))
      if (c1) setAviso(tr("{0} na posição {1} de {2}", nomeDe(c1, s, saida?.originais || []), acharS(c1, s.id) + 1, c1.itens.length))
    }
    selecionar(s, true)
  }
  function coluna(s: NonNullable<Sel>, passo: number) {
    if (s.tipo !== 'w') return
    const c1 = mudarC(c => colunaW(c, s.id, passo))
    if (c1) { refletir(c1, s.id); setAviso(tr("{0} movido para {1}", NOMES[widget(c1, s.id)?.tipo || 'titulo'], ondeEsta(c1, s.id))) }
    selecionar(s, true)
  }
  function duplicar(s: NonNullable<Sel>) {
    const c0 = docRef.current?.c
    if (!c0) return
    const [c1, nid] = s.tipo === 'w' ? duplicarW(c0, s.id) : duplicarS(c0, s.id)
    if (c1 === c0) return
    mudarC(() => c1, { anuncio: tr("Duplicado") })
    selecionar({ tipo: s.tipo, id: nid })
  }
  function apagar(s: NonNullable<Sel>) {
    const c0 = docRef.current?.c
    if (!c0) return
    const it = s.tipo === 's' ? item(c0, s.id) : null
    if (it?.tipo === 'original') { mudarC(c => alternarOculto(c, s.id)); return }
    const pai = s.tipo === 'w' ? secaoDe(c0, s.id) : null
    const nome = nomeDe(c0, s, saida?.originais || [])
    if (s.tipo === 'w') ponte()?.tirarNo(s.id)
    const nasCamadas = !!(document.activeElement as HTMLElement | null)?.closest('.ed-camadas')
    if (mudarC(c => s.tipo === 'w' ? tirarW(c, s.id) : tirarS(c, s.id), { anuncio: tr("{0} apagado (Ctrl+Z desfaz)", nome) })) {
      selecionar(pai ? { tipo: 's', id: pai.id } : null)
      if (nasCamadas && pai) requestAnimationFrame(() => document.querySelector<HTMLElement>(`.ed-camadas [data-camada="${pai.id}"]`)?.focus())
    }
  }
  function navegar(passo: number) {
    const c = docRef.current?.c
    if (!c) return
    const lista = ordem(c)
    const s = selRef.current
    const i = s ? lista.findIndex(x => x.tipo === s.tipo && x.id === s.id) : -1
    const alvo = lista[Math.max(0, Math.min(lista.length - 1, i < 0 ? 0 : i + passo))]
    if (!alvo) return
    selecionar(alvo, true)
    setAviso(nomeDe(c, alvo, saida?.originais || []))
    // com o foco nas Camadas, o foco anda junto (Enter no item escolhido escreve nele)
    if ((document.activeElement as HTMLElement | null)?.closest('.ed-camadas'))
      requestAnimationFrame(() => document.querySelector<HTMLElement>(`.ed-camadas [data-camada="${alvo.id}"]`)?.focus())
  }

  function teclar(e: KeyboardEvent) {
    const mod = e.ctrlKey || e.metaKey
    const k = e.key.toLowerCase()
    if (mod && k === 'z' && !e.shiftKey) { e.preventDefault(); desfazer(); return }
    if (mod && (k === 'y' || (k === 'z' && e.shiftKey))) { e.preventDefault(); desfazer(false); return }
    if (mod && k === 's') { e.preventDefault(); enviar(); return }
    if (mod && k === 'k') { e.preventDefault(); if (editRef.current) setBalao({ qual: 'linkTexto', vez: Date.now() }); return }
    if (!gerente) return
    const s = selRef.current
    const c = docRef.current?.c
    if (e.key === 'Escape') {
      e.preventDefault()
      if (porTocar) setPorTocar(null)
      else if (s?.tipo === 'w' && c) { const sc = secaoDe(c, s.id); selecionar(sc ? { tipo: 's', id: sc.id } : null) }
      else selecionar(null)
      return
    }
    if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
      e.preventDefault()
      const p = e.key === 'ArrowUp' ? -1 : 1
      if (e.altKey && s) mover(s, p)
      else navegar(p)
      return
    }
    if (!s || !c) return
    if (e.altKey && (e.key === 'ArrowLeft' || e.key === 'ArrowRight')) { e.preventDefault(); coluna(s, e.key === 'ArrowLeft' ? -1 : 1); return }
    if (e.key === 'Enter') {
      e.preventDefault()
      if (s.tipo === 'w') editarTexto(s.id)
      else { const it = item(c, s.id); const w = it?.tipo === 'secao' ? it.itens.flat()[0] : null; if (w) selecionar({ tipo: 'w', id: w.id }, true) }
      return
    }
    if (mod && k === 'd') { e.preventDefault(); duplicar(s); return }
    if (e.key === 'Delete' || e.key === 'Backspace') { e.preventDefault(); apagar(s) }
  }
  // as mesmas teclas com o foco no painel (Camadas, barra), menos dentro de um campo de escrever
  useEffect(() => {
    const f = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null
      if (t?.closest('input, textarea, select, [contenteditable]') && !((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's')) return
      if (t?.closest('button, a, summary') && (e.key === 'Enter' || e.key === ' ')) return
      if (t && t !== document.body && !t.closest('.ed, .ed-fora')) return      // o foco está em outra parte do painel
      ganchos.current?.tecla(e)
    }
    window.addEventListener('keydown', f)
    return () => window.removeEventListener('keydown', f)
  }, [])
  useEffect(() => { reposicionar() }, [tela, estreito, aba])

  // ------------------------------------------------------------------ a paleta arrastando até a prévia
  function arrastarDaPaleta(p: Peca, e: PE<HTMLButtonElement>) {
    if (!gerente || e.pointerType === 'touch' || e.button !== 0 || estreito) return
    const botao = e.currentTarget
    const x0 = e.clientX, y0 = e.clientY
    let ativo = false
    let dentro = false
    try { botao.setPointerCapture(e.pointerId) } catch { /* sem captura: a tampa resolve */ }
    const mover = (ev: PointerEvent) => {
      if (!ativo && Math.hypot(ev.clientX - x0, ev.clientY - y0) < 6) return
      if (!ativo) { ativo = true; setTampa(true) }
      setFantasma({ nome: nomeDaPeca(p), x: ev.clientX, y: ev.clientY })
      const pt = ponte()
      const q = lona.current?.paraDentro(ev.clientX, ev.clientY)
      const t = pt ? { w: pt.win.innerWidth, h: pt.win.innerHeight } : null
      dentro = !!(q && t && q.x >= 0 && q.y >= 0 && q.x <= t.w && q.y <= t.h)
      if (pt && q && dentro) pt.moverDeFora(q.x, q.y)
      else pt?.cancelarArrasto()
    }
    const fim = (soltou: boolean) => {
      botao.removeEventListener('pointermove', mover)
      botao.removeEventListener('pointerup', aoSoltar)
      botao.removeEventListener('pointercancel', aoCancelar)
      setTampa(false); setFantasma(null)
      if (!ativo) return
      engolirClique.current = true
      window.setTimeout(() => { engolirClique.current = false }, 300)
      const pt = ponte()
      const d = soltou && dentro && pt ? pt.soltarDeFora() : (pt?.cancelarArrasto(), null)
      if (d) inserir(p, d)
    }
    const aoSoltar = () => fim(true)
    const aoCancelar = () => fim(false)
    botao.addEventListener('pointermove', mover)
    botao.addEventListener('pointerup', aoSoltar)
    botao.addEventListener('pointercancel', aoCancelar)
  }
  function escolherDaPaleta(p: Peca) {
    if (engolirClique.current) { engolirClique.current = false; return }
    if (estreito) { setFolha(null); setPorTocar(p); setAviso(tr("Toque na página onde quer pôr: {0}", nomeDaPeca(p))); return }
    inserir(p, null)
  }

  // ------------------------------------------------------------------ publicar e versões
  async function acao(caminho: string, ok: string, corpo?: unknown) {
    try {
      const r = await api.post<Saida>(`/site/editor/paginas/${id}/${caminho}`, corpo)
      saidaRef.current = r; setSaida(r)
      toast(ok, 'ok')
      if (versoes) abrirVersoes()
    } catch (er) {
      const e = er as ApiError
      if (e.status === 409) { parado.current = true; setSalvo('conflito'); setErroSalvar(e.message) }
      toast(e.message, 'crit')
    }
  }
  async function abrirVersoes() {
    try { setVersoes((await api.get<{ versoes: Versao[] }>(`/site/editor/paginas/${id}/versoes`)).versoes) }
    catch (er) { toast((er as ApiError).message, 'crit') }
  }
  async function voltarVersao(vid: number) {
    try {
      const r = await api.post<Saida>(`/site/editor/paginas/${id}/versoes/${vid}/voltar`)
      ponte()?.pararEdicao()
      rev.current = r.pagina.rev
      saidaRef.current = r; setSaida(r)
      definir({ c: r.pagina.draft, seo: { title: r.pagina.title, description: r.pagina.description, path: r.pagina.path } })
      versaoSalva.current = versaoLocal.current
      hist.current.limpar()
      selecionar(null)
      lona.current?.recarregar()
      toast(tr("A versão voltou para o rascunho: confira e publique."), 'ok')
    } catch (er) { toast((er as ApiError).message, 'crit') }
  }

  if (l.error && !l.data) return <ErrorState error={l.error} retry={l.reload} />
  const atual = saida || l.data
  if (!atual || !doc) return <Loading />
  const p = atual.pagina
  const c = doc.c
  const originais = atual.originais
  const listaErros = Object.values(erros)
  const pend = atual.problemas.length + listaErros.length
  const salvando = salvo === 'salvando' || versaoLocal.current !== versaoSalva.current
  const podePublicar = gerente && !salvando && salvo === 'salvo' && pend === 0

  // a barra do que está selecionado
  const w = sel?.tipo === 'w' ? widget(c, sel.id) : null
  const it = sel?.tipo === 's' ? item(c, sel.id) : null
  const lg = w ? acharW(c, w.id) : null
  const sIdx = it ? acharS(c, it.id) : -1
  const pode = w && lg ? { cima: passoW(c, w.id, -1) !== c, baixo: passoW(c, w.id, 1) !== c, esq: lg.c > 0, dir: lg.c < (c.itens[lg.s] as Secao).colunas - 1 }
    : { cima: sIdx > 0, baixo: sIdx >= 0 && sIdx < c.itens.length - 1, esq: false, dir: false }
  const acoes: AcoesBarra = {
    mudarW: (x, chave) => { if (!w) return; mudarC(cc => mudarW(cc, w.id, x), { chave, desenhar: true }) },
    mudarS: x => { if (it) mudarC(cc => mudarS(cc, it.id, x)) },
    oculto: () => { if (it) mudarC(cc => alternarOculto(cc, it.id)) },
    passo: n => sel && mover(sel, n),
    coluna: n => sel && coluna(sel, n),
    duplicar: () => sel && duplicar(sel),
    apagar: () => sel && apagar(sel),
    editar: () => w && editarTexto(w.id),
    parar: () => ponte()?.pararEdicao(),
    comando: cmd => ponte()?.comando(cmd),
    linkNoTexto: url => ponte()?.comando('createLink', url),
    trocarFoto: () => { if (w) { fotoPara.current = { tipo: 'troca', id: w.id }; arquivo.current?.click() } },
    legenda: () => { if (w) { mudarC(cc => mudarW(cc, w.id, { legenda: 'Caption' })); editarDepois.current = w.id } },
    fechar: () => selecionar(null),
  }
  const barra = gerente && sel && (w || it) ? <Barra key={sel.id} w={w} it={it} nome={nomeDe(c, sel, originais)} editando={!!editando && editando === w?.id}
    h1Ocupado={(ponte()?.contarH1(w?.id) || 0) > 0} erro={w ? erros[w.id] : undefined} pode={pode} a={acoes} estreito={estreito}
    ancora={ancora} limites={limites} balao={balao} /> : null

  const painel = (qual: Aba) => qual === 'inserir'
    ? <Paleta aoEscolher={escolherDaPaleta} aoArrastar={arrastarDaPaleta} estreito={estreito} />
    : qual === 'camadas'
      ? <Camadas c={c} originais={originais} sel={sel} erros={erros} gerente={gerente} selecionar={s => {
          const ja = selRef.current?.tipo === s.tipo && selRef.current.id === s.id
          if (estreito) setFolha(null)
          selecionar(s, true)
          if (ja && s.tipo === 'w') editarTexto(s.id)
        }}
        passo={mover} coluna={coluna} apagar={apagar} oculto={x => mudarC(cc => alternarOculto(cc, x))} />
      : <PaginaPainel p={p} seo={doc.seo} gerente={gerente} problemas={atual.problemas} erros={listaErros} mudarSeo={mudarSeo}
        despublicar={() => acao('despublicar', p.base ? tr("O site voltou à página original.") : tr("A página saiu do ar."))}
        versoes={versoes} abrirVersoes={abrirVersoes} voltarVersao={voltarVersao} recarregar={() => lona.current?.recarregar()} />
  const abas = (onde: 'lado' | 'folha') => <div className="seg ed-abas" role="tablist" aria-label={tr("Painéis do editor")}>
    {ABAS.filter(([k]) => gerente || k !== 'inserir').map(([k, n]) => {
      const on = onde === 'lado' ? aba === k : folha === k
      return <button key={k} type="button" role="tab" aria-selected={on} className={`btn sm${on ? '' : ' ghost'}`}
        onClick={() => onde === 'lado' ? setAba(k) : setFolha(k)}>{n}{k === 'pagina' && pend > 0 ? ` (${pend})` : ''}</button>
    })}</div>
  const abaLado: Aba = !gerente && aba === 'inserir' ? 'camadas' : aba

  return <div className="ed">
    <input ref={arquivo} type="file" accept="image/*" className="sr-only" tabIndex={-1} aria-hidden="true"
      onChange={e => { const f = e.target.files?.[0]; const d = fotoPara.current; fotoPara.current = null; e.target.value = ''; if (f && d) subirFoto(f, d) }} />
    <div className="ed-topo">
      <Link className="btn sm ghost" to="/site/editor">{tr("← Páginas")}</Link>
      <h2 className="h2 ed-nome">{doc.seo.title || p.path}</h2>
      <Chip tone={ESTADO[p.estado][1]}>{ESTADO[p.estado][0]}</Chip>
      {gerente && <span className={`small ed-salvo${salvo === 'erro' || salvo === 'conflito' ? ' ruim' : ''}`} role="status">
        {salvo === 'conflito' ? tr("parado: outra pessoa salvou") : salvo === 'erro' ? tr("não salvou") : salvando ? tr("salvando…") : tr("salvo")}</span>}
      <div className="grow" />
      {gerente && <>
        <button type="button" className="btn sm ghost" aria-label={tr("Desfazer (Ctrl+Z)")} title={tr("Desfazer (Ctrl+Z)")} disabled={!hist.current.podeDesfazer} onClick={() => desfazer()}>↶</button>
        <button type="button" className="btn sm ghost" aria-label={tr("Refazer (Ctrl+Shift+Z)")} title={tr("Refazer (Ctrl+Shift+Z)")} disabled={!hist.current.podeRefazer} onClick={() => desfazer(false)}>↷</button></>}
      {!estreito && <div className="seg" role="group" aria-label={tr("Tamanho da prévia")}>
        <button type="button" className={`btn sm${tela === 'celular' ? '' : ' ghost'}`} aria-pressed={tela === 'celular'} onClick={() => setTela('celular')}>{tr("Celular")}</button>
        <button type="button" className={`btn sm${tela === 'computador' ? '' : ' ghost'}`} aria-pressed={tela === 'computador'} onClick={() => setTela('computador')}>{tr("Computador")}</button>
      </div>}
      {gerente && pend > 0 && <button type="button" className="btn sm ghost ed-pend" onClick={() => estreito ? setFolha('pagina') : setAba('pagina')}>
        {tr("{0} pendência(s)", pend)}</button>}
      {gerente && <button type="button" className="btn primary" disabled={!podePublicar} title={pend ? tr("Veja as pendências na aba Página") : undefined}
        onClick={() => acao('publicar', tr("Publicado: o site já mostra."), { rev: rev.current })}>{tr("Publicar")}</button>}
    </div>
    {(salvo === 'erro' || salvo === 'conflito') && <div className="ed-aviso" role="alert">
      <span className="grow">{salvo === 'conflito' ? tr("Outra pessoa (ou outra aba) salvou esta página. Recarregue para ver o que ela fez; o que você mudou depois disso não foi salvo.")
        : tr("Não salvou: {0}", erroSalvar)}</span>
      {salvo === 'conflito' ? <button type="button" className="btn sm" onClick={() => window.location.reload()}>{tr("Recarregar")}</button>
        : <button type="button" className="btn sm" onClick={() => enviar()}>{tr("Tentar de novo")}</button>}
    </div>}
    <div className="ed-corpo">
      {!estreito && <aside className="ed-lado" aria-label={tr("Inserir, camadas e página")}>
        {abas('lado')}
        <h2 className="h2 ed-lado-h">{ABAS.find(([k]) => k === abaLado)?.[1]}</h2>
        {painel(abaLado)}
      </aside>}
      <div className="ed-palco">
        {porTocar && <div className="ed-tocar" role="status"><span className="grow">{tr("Toque na página onde quer pôr: {0}", nomeDaPeca(porTocar))}</span>
          <button type="button" className="btn sm" onClick={() => setPorTocar(null)}>{tr("Cancelar")}</button></div>}
        <Lona ref={lona} src={atual.previa} tela={tela} estreito={estreito} editar={gerente} ganchos={pegarGanchos} dica={dica} tampa={tampa}
          aoLigar={pt => { pt.sincronizar(docRef.current?.c || c); pt.marcar(selRef.current); pt.marcarErros(Object.keys(errosRef.current))
            if (versaoLocal.current !== versaoSalva.current) agendar(true, 0)
            reposicionar() }} />
        {!estreito && barra}
      </div>
    </div>
    {/* o que fica preso na tela vai direto no <body>: o invólucro animado da página viraria a referência do fixed */}
    {createPortal(<div className="ed-fora">
      {estreito && gerente && <div className="ed-doca" style={teclado ? { bottom: teclado + 8 } : undefined}>
        {barra || <div className="ed-barra ed-barra-baixo ed-doca-geral">
          <button type="button" className="btn sm" onClick={() => setFolha('inserir')}><Icon name="plus" size={16} /> {tr("Inserir")}</button>
          <button type="button" className="btn sm ghost" onClick={() => setFolha('camadas')}>{tr("Camadas")}</button>
          <button type="button" className="btn sm ghost" onClick={() => setFolha('pagina')}>{tr("Página")}{pend ? ` (${pend})` : ''}</button>
        </div>}
      </div>}
      {estreito && !gerente && <div className="ed-doca"><div className="ed-barra ed-barra-baixo ed-doca-geral">
        <button type="button" className="btn sm ghost" onClick={() => setFolha('camadas')}>{tr("Camadas")}</button>
        <button type="button" className="btn sm ghost" onClick={() => setFolha('pagina')}>{tr("Página")}</button></div></div>}
      {estreito && folha && <>
        <div className="ed-folha-fundo" onClick={() => setFolha(null)} />
        <div className="ed-folha" role="dialog" aria-modal="true" aria-label={ABAS.find(([k]) => k === folha)?.[1]}>
          <div className="row" style={{ gap: 8, marginBottom: 10 }}>
            <h2 className="h2 grow" style={{ margin: 0 }}>{ABAS.find(([k]) => k === folha)?.[1]}</h2>
            <button type="button" className="btn sm ghost" aria-label={tr("Fechar")} onClick={() => setFolha(null)}><Icon name="x" size={16} /></button>
          </div>
          {abas('folha')}
          {painel(folha)}
        </div></>}
      {fantasma && <div className="ed-fantasma" style={{ transform: `translate(${fantasma.x + 12}px, ${fantasma.y + 12}px)` }} aria-hidden="true">{fantasma.nome}</div>}
    </div>, document.body)}
    <div className="sr-only" aria-live="polite">{aviso}</div>
  </div>
}
