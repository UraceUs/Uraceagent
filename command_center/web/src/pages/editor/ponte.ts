/* Editor do site como o Canva (#315): a ponte entre o painel e a prévia.
 *
 * A prévia é a página do site de verdade num iframe da mesma origem (a largura real, o CSS do site, as faixas
 * originais com os scripts delas). O painel mexe direto no documento dela, sem script novo lá dentro:
 * - lá dentro só entram classes e atributos (a política do site não deixa estilo inline): ed-hover, ed-sel,
 *   ed-solta-*, ed-arrastando, ed-erro, data-ed-dica e contenteditable; o CSS é o /_s/editor-previa.css;
 * - os eventos vêm de outro "realm" do navegador: nada de `instanceof HTMLElement`, só `nodeType` e `closest`;
 * - nada navega: clique em link, envio de formulário e o abrir/fechar das perguntas ficam parados.
 *
 * O painel recebe o que aconteceu pelos `Ganchos` e decide (selecionar, editar, mover). A ponte desenha a
 * seleção, põe o texto em edição, calcula onde uma coisa arrastada cai e troca só as seções que mudaram. */
import { limparHtml, linhas, umaLinha } from './texto'
import type { Conteudo, Destino, Sel, Tipo, W } from './tipos'

export interface Ganchos {
  /** Clique (ou toque) numa peça da prévia. `x`/`y` são da prévia. */
  clique(sel: Sel, ev: { duplo: boolean; x: number; y: number }): void
  /** O texto em edição mudou: `valor` é o que ele virou no modelo. */
  digitou(id: string, valor: Partial<W>): void
  saiuDaEdicao(): void
  /** Tecla dentro da prévia (fora do texto em edição, ou atalho dentro dele). */
  tecla(e: KeyboardEvent): void
  /** Arrastou e soltou um elemento (`Destino`) ou uma seção (o índice novo). */
  arrastou(oQue: NonNullable<Sel>, d: Destino | number): void
  /** Soltou um arquivo do computador: foto nova no lugar, ou troca a foto da imagem. */
  arquivo(f: File, d: Destino | { tipo: 'troca'; id: string }): void
  /** A prévia rolou ou mudou de tamanho: a barra flutuante se reposiciona. */
  mudouVista(): void
}

export type Alvo = { d: Destino | number | { tipo: 'troca'; id: string }; marca: Element; como: 'antes' | 'depois' | 'dentro' }

const ehDestino = (d: Alvo['d']): d is Destino => typeof d === 'object' && d !== null && (d.tipo === 'col' || d.tipo === 'nova')
const SOLTA = ['ed-solta-antes', 'ed-solta-depois', 'ed-solta-dentro']
const DE_PASSAGEM = ['ed-hover', 'ed-sel', 'ed-erro', 'ed-arrastando', ...SOLTA]
const ID = /^[a-z0-9]+$/

const comoElemento = (t: EventTarget | null): Element | null => {
  const n = t as Node | null
  if (!n) return null
  return n.nodeType === 1 ? n as Element : n.parentElement
}

/** O HTML de uma seção sem o que o painel pôs nela (para saber se o servidor mandou algo diferente). */
function assinatura(el: Element): string {
  const c = el.cloneNode(true) as Element
  for (const n of [c, ...Array.from(c.querySelectorAll('*'))]) {
    n.classList.remove(...DE_PASSAGEM)
    if (n.getAttribute('class') === '') n.removeAttribute('class')
    n.removeAttribute('data-ed-dica')
    n.removeAttribute('contenteditable')
  }
  return c.outerHTML
}

interface Arrasto { oQue: NonNullable<Sel>; no: Element; x0: number; y0: number; toque: boolean; ativo: boolean; timer: number }
interface Edicao { id: string; tipo: Tipo; raiz: HTMLElement; nos: HTMLElement[]; rico: boolean }

export class Ponte {
  readonly doc: Document
  readonly win: Window
  private ganchos: () => Ganchos
  private editar: boolean
  private dica: (tipo: string) => string
  private fora: (() => void)[] = []
  private hover: Element | null = null
  private sel: Sel = null
  private erros: string[] = []
  private ed: Edicao | null = null
  private faixa: Range | null = null
  private arrasto: Arrasto | null = null
  private ponteiro: { x: number; y: number; modo: 'w' | 's' | 'novo' } | null = null
  private alvo: Alvo | null = null
  private quadro = 0
  private engolirClique = false
  /** Seções que o servidor redesenhou mas ficaram como estavam porque tinham o texto em edição. */
  private puladas = new Set<string>()

  constructor(doc: Document, ganchos: () => Ganchos, editar: boolean, dica: (tipo: string) => string) {
    this.doc = doc
    this.win = doc.defaultView as Window
    this.ganchos = ganchos
    this.editar = editar
    this.dica = dica
  }

  private on(alvo: EventTarget, tipo: string, fn: (e: Event) => void, opts?: AddEventListenerOptions | boolean) {
    alvo.addEventListener(tipo, fn, opts)
    this.fora.push(() => alvo.removeEventListener(tipo, fn, opts))
  }

  get main(): HTMLElement | null { return this.doc.getElementById('conteudo') }

  ligar() {
    const d = this.doc
    // nada navega dentro da prévia (o iframe também está em sandbox, sem formulário nem janela nova)
    this.on(d, 'click', e => this.aoClicar(e as MouseEvent), true)
    this.on(d, 'auxclick', e => e.preventDefault(), true)
    this.on(d, 'submit', e => e.preventDefault(), true)
    if (!this.editar) return
    d.documentElement.classList.add('ed-modo')
    this.on(d, 'dblclick', e => this.aoClicar(e as MouseEvent, true), true)
    this.on(d, 'pointerdown', e => this.aoApertar(e as PointerEvent), true)
    this.on(d, 'pointermove', e => this.aoMover(e as PointerEvent), true)
    this.on(d, 'pointerup', e => this.aoSoltar(e as PointerEvent), true)
    this.on(d, 'pointercancel', () => this.cancelarArrasto(), true)
    this.on(d.documentElement, 'pointerleave', () => this.marcarHover(null))
    // depois do toque longo, o dedo arrasta a peça e não a página
    this.on(d, 'touchmove', e => { if (this.arrasto?.ativo) e.preventDefault() }, { passive: false, capture: true })
    this.on(d, 'contextmenu', e => { if (this.arrasto || !this.ed) e.preventDefault() }, true)
    this.on(d, 'dragstart', e => { if (!this.ed) e.preventDefault() }, true)      // a foto e o link não saem arrastados
    this.on(d, 'keydown', e => this.aoTeclar(e as KeyboardEvent), true)
    this.on(d, 'input', e => this.aoDigitar(e), true)
    this.on(d, 'beforeinput', e => this.antesDeDigitar(e as InputEvent), true)
    this.on(d, 'paste', e => this.aoColar(e as ClipboardEvent), true)
    this.on(d, 'drop', e => this.aoLargarArquivo(e as DragEvent), true)
    this.on(d, 'dragover', e => this.aoPassarArquivo(e as DragEvent), true)
    this.on(d, 'dragleave', e => { if (!(e as DragEvent).relatedTarget) this.limparSolta() }, true)
    this.on(d, 'selectionchange', () => this.guardarFaixa())
    this.on(this.win, 'scroll', () => this.ganchos().mudouVista(), { passive: true })
    this.on(this.win, 'resize', () => this.ganchos().mudouVista())
    this.rotular(d)
  }

  desligar() {
    this.cancelarArrasto()
    this.fora.forEach(f => f())
    this.fora = []
  }

  // ------------------------------------------------------------------ achar as peças
  no(sel: Sel): HTMLElement | null {
    if (!sel || !ID.test(sel.id)) return null
    return this.doc.querySelector(sel.tipo === 'w' ? `[data-ed-w="${sel.id}"]` : `[data-ed-s="${sel.id}"]`)
  }
  selDe(el: Element | null): Sel {
    const w = el?.closest('[data-ed-w]')
    if (w) return { tipo: 'w', id: w.getAttribute('data-ed-w') || '' }
    const s = el?.closest('[data-ed-s]')
    if (s) return { tipo: 's', id: s.getAttribute('data-ed-s') || '' }
    return null
  }
  retangulo(sel: Sel): DOMRect | null { return this.no(sel)?.getBoundingClientRect() || null }
  rolarAte(sel: Sel) {
    const n = this.no(sel)
    if (!n) return
    const r = n.getBoundingClientRect()
    if (r.top < 0 || r.bottom > this.win.innerHeight) n.scrollIntoView({ block: r.height > this.win.innerHeight ? 'start' : 'center' })
  }
  /** Quantos h1 a página tem na prévia, fora o de `exceto` (as faixas escondidas não contam). */
  contarH1(exceto?: string): number {
    return Array.from(this.main?.querySelectorAll('h1') || [])
      .filter(h => !h.closest('[data-ed-oculto]') && (!exceto || h.closest('[data-ed-w]')?.getAttribute('data-ed-w') !== exceto)).length
  }

  // ------------------------------------------------------------------ seleção, hover e erros
  marcar(sel: Sel) {
    this.sel = sel
    this.doc.querySelectorAll('.ed-sel').forEach(n => n.classList.remove('ed-sel'))
    this.no(sel)?.classList.add('ed-sel')
  }
  private marcarHover(n: Element | null) {
    if (n === this.hover) return
    this.hover?.classList.remove('ed-hover')
    this.hover = n
    n?.classList.add('ed-hover')
  }
  marcarErros(ids: string[]) {
    this.erros = ids
    this.doc.querySelectorAll('.ed-erro').forEach(n => n.classList.remove('ed-erro'))
    for (const id of ids) this.no({ tipo: 'w', id })?.classList.add('ed-erro')
  }
  /** As dicas dos vazios ("Escreva o título"…), no idioma do painel. */
  rotular(raiz: ParentNode) {
    raiz.querySelectorAll('[data-ed-w]').forEach(el => {
      const t = el.getAttribute('data-ed-tipo') || ''
      const alvo = t === 'botao' ? el.querySelector('a') : t === 'lista' ? null : el
      alvo?.setAttribute('data-ed-dica', this.dica(t))
      if (t === 'lista') el.querySelectorAll('li').forEach(li => li.setAttribute('data-ed-dica', this.dica('item')))
      if (t === 'faq') {
        el.querySelectorAll('summary').forEach(s => s.setAttribute('data-ed-dica', this.dica('pergunta')))
        el.querySelectorAll('.faq-corpo p').forEach(p => p.setAttribute('data-ed-dica', this.dica('resposta')))
      }
    })
  }

  // ------------------------------------------------------------------ a página segue o modelo
  /** A ordem das seções, as que saíram e as faixas escondidas, na hora (sem esperar o servidor). A seção nova ganha
   *  um esqueleto com as colunas (para já poder soltar nela) até o HTML de verdade chegar. */
  sincronizar(c: Conteudo) {
    const main = this.main
    if (!main) return
    const nos = new Map<string, Element>()
    for (const n of Array.from(main.children)) { const id = n.getAttribute('data-ed-s'); if (id) nos.set(id, n) }
    const quer = new Set(c.itens.map(x => x.id))
    for (const [id, n] of nos) if (!quer.has(id)) { n.remove(); nos.delete(id) }
    let antes: Element | null = null
    for (const it of c.itens) {
      let n = nos.get(it.id)
      if (!n) {
        if (it.tipo !== 'secao') continue
        n = this.esqueleto(it.id, it.colunas)
      }
      const esperado: Element | null = antes ? antes.nextElementSibling : main.firstElementChild
      if (n !== esperado) main.insertBefore(n, esperado)
      if (it.tipo === 'original') n.toggleAttribute('data-ed-oculto', !!it.oculto)
      antes = n
    }
    this.marcar(this.sel)
  }
  private esqueleto(id: string, colunas: number): Element {
    const d = this.doc
    const s = d.createElement('section')
    s.className = 'faixa clara ed-secao ed-esp-m ed-esqueleto'
    s.setAttribute('data-ed-s', id)
    const l = d.createElement('div'); l.className = 'largura'
    const g = d.createElement('div'); g.className = `ed-grade ed-c${colunas}`
    for (let k = 0; k < colunas; k++) { const c = d.createElement('div'); c.className = 'ed-col'; c.setAttribute('data-ed-col', `${id}:${k}`); g.appendChild(c) }
    l.appendChild(g); s.appendChild(l)
    return s
  }

  /** Troca só as seções que o servidor desenhou diferente. A que tem o texto em edição fica (o cursor não pula). */
  aplicarSecoes(secoes: { id: string; html: string }[]) {
    const main = this.main
    if (!main) return
    for (const { id, html } of secoes) {
      if (!ID.test(id)) continue
      const n = main.querySelector(`:scope > [data-ed-s="${id}"]`)
      if (!n) continue
      if ((this.ed && n.contains(this.ed.raiz)) || (this.arrasto?.ativo && n.contains(this.arrasto.no))) { this.puladas.add(id); continue }
      this.puladas.delete(id)
      const t = this.doc.createElement('template')
      t.innerHTML = html
      const novo = t.content.firstElementChild
      if (!novo || (!n.classList.contains('ed-esqueleto') && assinatura(n) === novo.outerHTML)) continue
      n.replaceWith(novo)
      this.rotular(novo)
    }
    this.marcar(this.sel)
    this.marcarErros(this.erros)
  }

  /** Ficou seção para trocar depois (o texto em edição ou o arrasto seguravam)? */
  get temPulada() { return this.puladas.size > 0 }

  /** Põe o nó do elemento onde o modelo diz (coluna `c` da seção `sid`, posição `i`), na hora: o servidor confirma
   *  depois. */
  moverNo(id: string, sid: string, c: number, i: number) {
    const n = this.no({ tipo: 'w', id })
    if (!n || !ID.test(sid)) return
    const col = this.doc.querySelector(`[data-ed-col="${sid}:${c}"]`)
    if (!col) return
    const filhos = Array.from(col.children).filter(x => x.hasAttribute('data-ed-w') && x !== n)
    col.insertBefore(n, filhos[i] || null)
  }
  tirarNo(id: string) { this.no({ tipo: 'w', id })?.remove() }

  // ------------------------------------------------------------------ texto no lugar
  get editando(): string | null { return this.ed?.id || null }

  /** Põe o texto do elemento em edição: o cursor no ponto clicado, ou no fim; `tudo` marca o texto inteiro (o
   *  elemento que acabou de entrar: escrever já troca o texto de exemplo). Devolve se deu. */
  editarTexto(id: string, ponto?: { x: number; y: number }, tudo = false): boolean {
    const raiz = this.no({ tipo: 'w', id })
    if (!raiz) return false
    const tipo = raiz.getAttribute('data-ed-tipo') as Tipo
    let nos: HTMLElement[] = []
    const rico = tipo === 'texto'
    if (tipo === 'titulo' || tipo === 'texto' || tipo === 'lista') nos = [raiz]
    else if (tipo === 'botao') nos = Array.from(raiz.querySelectorAll<HTMLElement>('a'))
    else if (tipo === 'imagem') nos = Array.from(raiz.querySelectorAll<HTMLElement>('figcaption'))
    else if (tipo === 'faq') {
      raiz.querySelectorAll('details').forEach(x => x.setAttribute('open', ''))
      nos = Array.from(raiz.querySelectorAll<HTMLElement>('summary, .faq-corpo'))
    }
    if (!nos.length) return false
    this.pararEdicao()
    for (const n of nos) {
      if (rico || tipo === 'lista') n.setAttribute('contenteditable', 'true')
      else {
        n.setAttribute('contenteditable', 'plaintext-only')
        if (n.contentEditable !== 'plaintext-only') n.setAttribute('contenteditable', 'true')   // navegador sem o modo
      }
    }
    if (rico) try { this.doc.execCommand('defaultParagraphSeparator', false, 'p') } catch { /* navegador antigo */ }
    this.ed = { id, tipo, raiz, nos, rico }
    const noPonto = ponto ? comoElemento(this.doc.elementFromPoint(ponto.x, ponto.y)) : null
    const foco = nos.find(n => noPonto && n.contains(noPonto)) || nos[0]
    foco.focus({ preventScroll: true })
    if (!(ponto && this.cursorEm(ponto.x, ponto.y, foco))) this.cursorNoFim(foco, tudo)
    this.ganchos().mudouVista()
    return true
  }
  private cursorEm(x: number, y: number, dentro: HTMLElement): boolean {
    const d = this.doc as Document & { caretRangeFromPoint?: (x: number, y: number) => Range | null
      caretPositionFromPoint?: (x: number, y: number) => { offsetNode: Node; offset: number } | null }
    let r: Range | null = null
    if (d.caretRangeFromPoint) r = d.caretRangeFromPoint(x, y)
    else if (d.caretPositionFromPoint) {
      const p = d.caretPositionFromPoint(x, y)
      if (p) { r = d.createRange(); r.setStart(p.offsetNode, p.offset); r.collapse(true) }
    }
    if (!r || !dentro.contains(r.startContainer)) return false
    const s = d.getSelection()
    s?.removeAllRanges(); s?.addRange(r)
    return true
  }
  private cursorNoFim(el: HTMLElement, tudo = false) {
    const r = this.doc.createRange()
    r.selectNodeContents(el)
    if (!tudo) r.collapse(false)
    const s = this.doc.getSelection()
    s?.removeAllRanges(); s?.addRange(r)
  }
  pararEdicao() {
    const e = this.ed
    if (!e) return
    this.ed = null
    this.faixa = null
    for (const n of e.nos) n.removeAttribute('contenteditable')
    this.doc.getSelection()?.removeAllRanges()
    const ativo = this.doc.activeElement as HTMLElement | null
    if (ativo && ativo !== this.doc.body) ativo.blur?.()
    this.ganchos().saiuDaEdicao()
  }
  /** O que o texto em edição virou, no modelo. */
  ler(): { id: string; valor: Partial<W> } | null {
    const e = this.ed
    if (!e) return null
    const r = e.raiz
    switch (e.tipo) {
      case 'titulo': return { id: e.id, valor: { texto: umaLinha(r.textContent) } }
      case 'botao': return { id: e.id, valor: { texto: umaLinha(r.querySelector('a')?.textContent) } }
      case 'texto': return { id: e.id, valor: { html: limparHtml(r.innerHTML) } }
      case 'lista': return { id: e.id, valor: { itens: linhas(r) } }
      case 'imagem': return { id: e.id, valor: { legenda: umaLinha(r.querySelector('figcaption')?.textContent) } }
      case 'faq': return { id: e.id, valor: { itens: Array.from(r.querySelectorAll('details')).map(x => ({
        pergunta: umaLinha(x.querySelector('summary')?.textContent), resposta: umaLinha((x.querySelector('.faq-corpo') as HTMLElement | null)?.innerText) })) } }
      default: return null
    }
  }
  private guardarFaixa() {
    if (!this.ed) return
    const s = this.doc.getSelection()
    if (s && s.rangeCount && this.ed.nos.some(n => n.contains(s.anchorNode))) this.faixa = s.getRangeAt(0).cloneRange()
  }
  /** Negrito, itálico, lista e link no texto em edição (a barra do painel chama; o cursor volta para onde estava). */
  comando(cmd: string, arg?: string) {
    const e = this.ed
    if (!e) return
    const alvo = e.nos[0]
    alvo.focus({ preventScroll: true })
    if (this.faixa) { const s = this.doc.getSelection(); s?.removeAllRanges(); s?.addRange(this.faixa) }
    this.doc.execCommand(cmd, false, arg)
    const lido = this.ler()
    if (lido) this.ganchos().digitou(lido.id, lido.valor)
  }
  /** Há texto marcado no texto em edição (para o link)? */
  temMarcado(): boolean { return !!this.faixa && !this.faixa.collapsed }

  private aoDigitar(e: Event) {
    const ed = this.ed
    const el = comoElemento(e.target)
    if (!ed || !el || !ed.nos.some(n => n.contains(el))) return
    const lido = this.ler()
    if (lido) this.ganchos().digitou(lido.id, lido.valor)
    this.ganchos().mudouVista()
  }
  private antesDeDigitar(e: InputEvent) {
    if (!this.ed) return
    if (e.inputType === 'historyUndo' || e.inputType === 'historyRedo') { e.preventDefault(); return }   // o desfazer é o do painel
    if (this.ed.rico || this.ed.tipo === 'lista') {
      if (this.ed.tipo === 'lista' && e.inputType.startsWith('format')) e.preventDefault()
      return
    }
    if (e.inputType === 'insertParagraph' || e.inputType === 'insertLineBreak' || e.inputType.startsWith('format')) e.preventDefault()
  }
  private aoColar(e: ClipboardEvent) {
    if (!this.ed) return
    e.preventDefault()
    const dt = e.clipboardData
    if (!dt) return
    if (this.ed.rico) {
      const html = dt.getData('text/html')
      if (html) { this.doc.execCommand('insertHTML', false, limparHtml(html)); return }
    }
    const txt = dt.getData('text/plain') || ''
    this.doc.execCommand('insertText', false, this.ed.rico || this.ed.tipo === 'lista' ? txt : umaLinha(txt))
  }

  private aoTeclar(e: KeyboardEvent) {
    const ed = this.ed
    const el = comoElemento(e.target)
    const noTexto = !!ed && !!el && ed.nos.some(n => n.contains(el))
    if (noTexto && ed) {
      const mod = e.ctrlKey || e.metaKey
      if (e.key === 'Escape') { e.preventDefault(); this.pararEdicao(); return }
      if (mod && ['z', 'y'].includes(e.key.toLowerCase())) { this.ganchos().tecla(e); return }
      if (mod && ['s', 'k'].includes(e.key.toLowerCase())) { this.ganchos().tecla(e); return }
      if (!ed.rico && ed.tipo !== 'lista' && e.key === 'Enter') { e.preventDefault(); this.pararEdicao(); return }
      if (el?.closest('summary') && e.key === ' ') { e.preventDefault(); this.doc.execCommand('insertText', false, ' '); return }
      if (!ed.rico && mod && ['b', 'i', 'u'].includes(e.key.toLowerCase())) { e.preventDefault(); return }
      return
    }
    this.ganchos().tecla(e)
  }

  // ------------------------------------------------------------------ clique
  private aoClicar(e: MouseEvent, duplo = false) {
    const el = comoElemento(e.target)
    if (el?.closest('a, summary')) e.preventDefault()
    if (!this.editar || !el) return
    if (this.engolirClique) { this.engolirClique = false; e.preventDefault(); return }
    if (this.ed && this.ed.nos.some(n => n.contains(el))) return       // no texto em edição: o cursor vai onde clicou
    e.preventDefault()
    this.ganchos().clique(this.selDe(el), { duplo, x: e.clientX, y: e.clientY })
  }

  // ------------------------------------------------------------------ arrastar dentro da prévia (mouse e toque)
  private aoApertar(e: PointerEvent) {
    if (e.button !== 0 || this.arrasto) return
    const el = comoElemento(e.target)
    if (!el || (this.ed && this.ed.nos.some(n => n.contains(el)))) return
    const w = el.closest('[data-ed-w]')
    const s = el.closest('[data-ed-s]')
    const no = w || s
    if (!no) return
    const oQue: NonNullable<Sel> = w ? { tipo: 'w', id: w.getAttribute('data-ed-w') || '' } : { tipo: 's', id: s?.getAttribute('data-ed-s') || '' }
    const toque = e.pointerType !== 'mouse'
    this.arrasto = { oQue, no, x0: e.clientX, y0: e.clientY, toque, ativo: false, timer: 0 }
    if (toque) this.arrasto.timer = this.win.setTimeout(() => this.ativar(e.clientX, e.clientY), 350)   // toque longo
  }
  private ativar(x: number, y: number) {
    const a = this.arrasto
    if (!a || a.ativo) return
    if (this.ed) this.pararEdicao()
    a.ativo = true
    a.no.classList.add('ed-arrastando')
    this.doc.documentElement.classList.add('ed-arrasto')
    this.marcarHover(null)
    this.ponteiro = { x, y, modo: a.oQue.tipo }
    this.rolarSozinho()
    this.alvoDoPonteiro()
  }
  private aoMover(e: PointerEvent) {
    const a = this.arrasto
    if (!a) {
      if (e.pointerType === 'mouse' && !this.ponteiro) {
        const el = comoElemento(e.target)
        this.marcarHover(el ? el.closest('[data-ed-w]') || el.closest('[data-ed-s]') : null)
      }
      return
    }
    const dist = Math.hypot(e.clientX - a.x0, e.clientY - a.y0)
    if (!a.ativo) {
      if (!a.toque && dist > 6) this.ativar(e.clientX, e.clientY)
      else if (a.toque && dist > 10) this.cancelarArrasto()      // o dedo andou antes do toque longo: é rolar a página
      return
    }
    e.preventDefault()
    if (this.ponteiro) { this.ponteiro.x = e.clientX; this.ponteiro.y = e.clientY }
    this.alvoDoPonteiro()
  }
  private aoSoltar(e: PointerEvent) {
    const a = this.arrasto
    if (!a) return
    if (!a.ativo) { this.cancelarArrasto(); return }
    e.preventDefault()
    const alvo = this.alvo
    this.cancelarArrasto()
    this.engolirClique = true
    this.win.setTimeout(() => { this.engolirClique = false }, 400)
    if (alvo && typeof alvo.d === 'number') this.ganchos().arrastou(a.oQue, alvo.d)
    else if (alvo && ehDestino(alvo.d)) this.ganchos().arrastou(a.oQue, alvo.d)
  }
  cancelarArrasto() {
    const a = this.arrasto
    if (a) { this.win.clearTimeout(a.timer); a.no.classList.remove('ed-arrastando') }
    this.arrasto = null
    this.ponteiro = null
    this.doc.documentElement.classList.remove('ed-arrasto')
    this.win.cancelAnimationFrame(this.quadro)
    this.limparSolta()
  }
  private alvoDoPonteiro() {
    const p = this.ponteiro
    if (!p) return
    const a = this.destinoEm(p.x, p.y, p.modo, this.arrasto?.oQue.tipo === 'w' ? this.arrasto.oQue.id : undefined)
    this.mostrarSolta(a)
  }
  /** Perto da borda de cima ou de baixo, a prévia rola sozinha enquanto se arrasta. */
  private rolarSozinho() {
    this.win.cancelAnimationFrame(this.quadro)
    const passo = () => {
      const p = this.ponteiro
      if (!p) return
      const h = this.win.innerHeight
      const m = Math.min(64, h / 6)
      const dy = p.y < m ? -Math.ceil((m - p.y) / 3) : p.y > h - m ? Math.ceil((p.y - (h - m)) / 3) : 0
      if (dy) { this.win.scrollBy(0, dy); this.alvoDoPonteiro() }
      this.quadro = this.win.requestAnimationFrame(passo)
    }
    this.quadro = this.win.requestAnimationFrame(passo)
  }

  // ------------------------------------------------------------------ arrastar de fora (a paleta do painel)
  /** A paleta arrasta por cima da prévia: `x`/`y` já convertidos para a prévia (sem a escala). */
  moverDeFora(x: number, y: number) {
    if (!this.ponteiro) { this.ponteiro = { x, y, modo: 'novo' }; this.rolarSozinho() }
    this.ponteiro.x = x; this.ponteiro.y = y
    this.alvoDoPonteiro()
  }
  soltarDeFora(): Destino | null {
    const a = this.alvo
    this.cancelarArrasto()
    return a && ehDestino(a.d) ? a.d : null
  }
  /** Onde cai uma peça nova tocada ("toque onde quer pôr"). */
  destinoDoToque(x: number, y: number): Destino | null {
    const a = this.destinoEm(x, y, 'novo')
    return a && ehDestino(a.d) ? a.d : null
  }

  // ------------------------------------------------------------------ arquivo do computador
  private temArquivo(e: DragEvent) { return Array.from(e.dataTransfer?.types || []).includes('Files') }
  private alvoArquivo(x: number, y: number): Alvo | null {
    const img = comoElemento(this.doc.elementFromPoint(x, y))?.closest('[data-ed-tipo="imagem"]')
    if (img) return { d: { tipo: 'troca', id: img.getAttribute('data-ed-w') || '' }, marca: img, como: 'dentro' }
    return this.destinoEm(x, y, 'novo')
  }
  private aoPassarArquivo(e: DragEvent) {
    if (!this.temArquivo(e)) return
    e.preventDefault()
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy'
    this.mostrarSolta(this.alvoArquivo(e.clientX, e.clientY))
  }
  private aoLargarArquivo(e: DragEvent) {
    if (!this.temArquivo(e)) return
    e.preventDefault()
    const alvo = this.alvoArquivo(e.clientX, e.clientY)
    this.limparSolta()
    const f = Array.from(e.dataTransfer?.files || []).find(x => x.type.startsWith('image/'))
    if (f && alvo && typeof alvo.d !== 'number') this.ganchos().arquivo(f, alvo.d as Destino | { tipo: 'troca'; id: string })
  }

  // ------------------------------------------------------------------ onde cai
  private secoes(): Element[] {
    return Array.from(this.main?.children || []).filter(n => n.hasAttribute('data-ed-s'))
  }
  /** O alvo no ponto (`x`, `y` da prévia): para uma seção, o índice novo; para um elemento, a coluna e a posição, ou
   *  uma seção nova quando cai numa faixa original. `ignorar`: o elemento que está sendo arrastado. */
  destinoEm(x: number, y: number, modo: 'w' | 's' | 'novo', ignorar?: string): Alvo | null {
    const lista = this.secoes()
    if (!lista.length) return null
    if (modo === 's') {
      for (let k = 0; k < lista.length; k++) {
        const r = lista[k].getBoundingClientRect()
        if (y < r.top + r.height / 2) return { d: k, marca: lista[k], como: 'antes' }
      }
      return { d: lista.length, marca: lista[lista.length - 1], como: 'depois' }
    }
    const el = comoElemento(this.doc.elementFromPoint(x, y))
    let sec = el?.closest('[data-ed-s]') || null
    if (!sec || !lista.includes(sec)) {        // fora das seções (cabeçalho, rodapé): a mais perto
      const r0 = lista[0].getBoundingClientRect()
      sec = y < r0.top ? lista[0] : lista[lista.length - 1]
    }
    const idx = lista.indexOf(sec)
    const r = sec.getBoundingClientRect()
    if (sec.hasAttribute('data-ed-o')) {
      const antes = y < r.top + r.height / 2
      return { d: { tipo: 'nova', i: antes ? idx : idx + 1 }, marca: sec, como: antes ? 'antes' : 'depois' }
    }
    const cols = Array.from(sec.querySelectorAll('[data-ed-col]'))
    if (!cols.length) return null
    let col = el?.closest('[data-ed-col]') || null
    if (!col || !cols.includes(col)) {
      const dist = (c: Element) => { const b = c.getBoundingClientRect()
        return Math.hypot(Math.max(b.left - x, 0, x - b.right), Math.max(b.top - y, 0, y - b.bottom)) }
      col = cols.reduce((a, b) => dist(b) < dist(a) ? b : a)
    }
    const [sid, ci] = (col.getAttribute('data-ed-col') || ':0').split(':')
    const filhos = Array.from(col.children).filter(n => n.hasAttribute('data-ed-w'))
    for (let i = 0; i < filhos.length; i++) {
      const b = filhos[i].getBoundingClientRect()
      if (y < b.top + b.height / 2) {
        if (filhos[i].getAttribute('data-ed-w') === ignorar) return { d: { tipo: 'col', sid, c: Number(ci), i }, marca: filhos[i], como: 'dentro' }
        return { d: { tipo: 'col', sid, c: Number(ci), i }, marca: filhos[i], como: 'antes' }
      }
    }
    if (filhos.length) return { d: { tipo: 'col', sid, c: Number(ci), i: filhos.length }, marca: filhos[filhos.length - 1], como: 'depois' }
    return { d: { tipo: 'col', sid, c: Number(ci), i: 0 }, marca: col, como: 'dentro' }
  }
  private mostrarSolta(a: Alvo | null) {
    if (this.alvo?.marca !== a?.marca || this.alvo?.como !== a?.como) {
      this.limparSolta()
      if (a) a.marca.classList.add(`ed-solta-${a.como}`)
    }
    this.alvo = a
  }
  private limparSolta() {
    this.doc.querySelectorAll(SOLTA.map(c => '.' + c).join(',')).forEach(n => n.classList.remove(...SOLTA))
    this.alvo = null
  }
}
