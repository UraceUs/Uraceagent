/* Editor do site como o Canva (#315): as operações no modelo da página, puras (recebem um conteúdo e devolvem
 * outro, sem mexer no de entrada). A prévia, as Camadas, os atalhos e o desfazer usam só estas. */
import { tr } from '../../i18n'
import type { Conteudo, Destino, Item, Secao, Sel, Tipo, W } from './tipos'

export function novoId() {
  const b = new Uint8Array(4)
  crypto.getRandomValues(b)
  return Array.from(b, x => x.toString(16).padStart(2, '0')).join('')
}

export const NOMES: Record<Tipo, string> = { titulo: tr("Título"), texto: tr("Texto"), imagem: tr("Imagem"), botao: tr("Botão"), lista: tr("Lista"),
  espaco: tr("Espaço"), karts: tr("Karts e preços"), produtos: tr("Produtos da loja"), cartoes: tr("Cartões de uma página"), faq: tr("Perguntas frequentes") }
export const PALETA: Tipo[] = ['titulo', 'texto', 'imagem', 'botao', 'lista', 'espaco', 'faq', 'karts', 'produtos', 'cartoes']
/** Uma peça da paleta: um elemento, ou uma seção nova de 1 a 3 colunas. */
export type Peca = Tipo | 'secao1' | 'secao2' | 'secao3'
export const nomeDaPeca = (p: Peca) => p.startsWith('secao') ? tr("Seção de {0} coluna(s)", p.slice(5)) : NOMES[p as Tipo]
/** O que se escreve no lugar, na prévia. */
export const DE_ESCREVER: Tipo[] = ['titulo', 'texto', 'botao', 'lista', 'faq', 'imagem']

export function novoWidget(t: Tipo): W {
  const id = novoId()
  switch (t) {
    case 'titulo': return { id, tipo: t, texto: 'New title', nivel: 2, tamanho: 'm', cor: 'padrao', alinhar: 'esq' }
    case 'texto': return { id, tipo: t, html: '<p>Write here.</p>', tamanho: 'm', cor: 'padrao', alinhar: 'esq' }
    case 'botao': return { id, tipo: t, texto: 'Book now', link: '/services/arrive-and-drive/#reservar', estilo: 'cheio', alinhar: 'esq' }
    case 'lista': return { id, tipo: t, itens: ['First item'] }
    case 'espaco': return { id, tipo: t, tamanho: 'm' }
    case 'imagem': return { id, tipo: t, src: '', alt: '', forma: 'larga', legenda: '', largura: 1600, altura: 900 }
    case 'produtos': return { id, tipo: t, categoria: '', quantos: 6 }
    case 'cartoes': return { id, tipo: t, pagina: 'academy' }
    case 'faq': return { id, tipo: t, itens: [{ pergunta: 'Question?', resposta: 'Answer.' }] }
    default: return { id, tipo: t }
  }
}

export const novaSecao = (colunas = 1): Secao =>
  ({ id: novoId(), tipo: 'secao', fundo: 'clara', espaco: 'm', colunas, itens: Array.from({ length: colunas }, () => []) })

const copia = (c: Conteudo): Conteudo =>
  ({ itens: c.itens.map((x): Item => x.tipo === 'secao' ? { ...x, itens: x.itens.map(col => [...col]) } : { ...x }) })

export interface Lugar { s: number; c: number; i: number }

export function acharW(c: Conteudo, id: string): Lugar | null {
  for (let s = 0; s < c.itens.length; s++) {
    const it = c.itens[s]
    if (it.tipo !== 'secao') continue
    for (let k = 0; k < it.itens.length; k++) {
      const i = it.itens[k].findIndex(w => w.id === id)
      if (i >= 0) return { s, c: k, i }
    }
  }
  return null
}
export function widget(c: Conteudo, id: string): W | null {
  const l = acharW(c, id)
  return l ? (c.itens[l.s] as Secao).itens[l.c][l.i] : null
}
export const acharS = (c: Conteudo, id: string) => c.itens.findIndex(x => x.id === id)
export const item = (c: Conteudo, id: string): Item | null => c.itens[acharS(c, id)] || null
/** A seção de um elemento. */
export function secaoDe(c: Conteudo, wid: string): Secao | null {
  const l = acharW(c, wid)
  return l ? c.itens[l.s] as Secao : null
}

export function mudarW(c: Conteudo, id: string, x: Partial<W>): Conteudo {
  const l = acharW(c, id)
  if (!l) return c
  const n = copia(c)
  const col = (n.itens[l.s] as Secao).itens[l.c]
  col[l.i] = { ...col[l.i], ...x }
  return n
}

export function mudarS(c: Conteudo, id: string, x: Partial<Secao>): Conteudo {
  const s = acharS(c, id)
  const o = c.itens[s]
  if (!o || o.tipo !== 'secao') return c
  const n = copia(c)
  const sc: Secao = { ...(n.itens[s] as Secao), ...x }
  if (x.colunas) {         // menos colunas: o que estava nas de fora vai para a última que fica
    const cols = [...(n.itens[s] as Secao).itens]
    while (cols.length < x.colunas) cols.push([])
    while (cols.length > x.colunas) { const ult = cols.pop() || []; cols[cols.length - 1] = [...cols[cols.length - 1], ...ult] }
    sc.itens = cols
  }
  n.itens[s] = sc
  return n
}

export function alternarOculto(c: Conteudo, id: string): Conteudo {
  const s = acharS(c, id)
  const o = c.itens[s]
  if (!o || o.tipo !== 'original') return c
  const n = copia(c)
  n.itens[s] = { ...o, oculto: !o.oculto }
  return n
}

export function tirarW(c: Conteudo, id: string): Conteudo {
  const l = acharW(c, id)
  if (!l) return c
  const n = copia(c);
  (n.itens[l.s] as Secao).itens[l.c].splice(l.i, 1)
  return n
}

/** Apaga uma seção nova. A faixa original não se apaga: esconde (`alternarOculto`). */
export function tirarS(c: Conteudo, id: string): Conteudo {
  const o = item(c, id)
  if (!o || o.tipo !== 'secao') return c
  return { itens: copia(c).itens.filter(x => x.id !== id) }
}

export function porW(c: Conteudo, w: W, d: Destino): Conteudo {
  const n = copia(c)
  if (d.tipo === 'nova') {
    const sc = novaSecao(1)
    sc.itens[0].push(w)
    n.itens.splice(Math.max(0, Math.min(d.i, n.itens.length)), 0, sc)
    return n
  }
  const sc = n.itens[acharS(n, d.sid)]
  if (!sc || sc.tipo !== 'secao') return c
  const col = sc.itens[Math.max(0, Math.min(d.c, sc.itens.length - 1))]
  col.splice(Math.max(0, Math.min(d.i, col.length)), 0, w)
  return n
}

/** Leva um elemento para `d` (o índice de `d` é o de antes de tirar o elemento do lugar dele). */
export function moverW(c: Conteudo, id: string, d: Destino): Conteudo {
  const l = acharW(c, id)
  if (!l) return c
  const w = (c.itens[l.s] as Secao).itens[l.c][l.i]
  const alvo = d.tipo === 'col' && c.itens[l.s].id === d.sid && d.c === l.c && d.i > l.i ? { ...d, i: d.i - 1 } : d
  return porW(tirarW(c, id), w, alvo)
}

/** Leva o item (seção ou faixa) para antes do item que hoje está em `para` (`para` = tamanho: vai para o fim). */
export function moverS(c: Conteudo, id: string, para: number): Conteudo {
  const s = acharS(c, id)
  if (s < 0 || para === s || para === s + 1) return c
  const n = copia(c)
  const [x] = n.itens.splice(s, 1)
  n.itens.splice(s < para ? para - 1 : para, 0, x)
  return n
}
export function passoS(c: Conteudo, id: string, passo: number): Conteudo {
  const s = acharS(c, id)
  const t = s + passo
  if (s < 0 || t < 0 || t >= c.itens.length) return c
  return moverS(c, id, passo > 0 ? t + 1 : t)
}

/** Sobe ou desce um elemento; no começo ou no fim da coluna, passa para a seção de cima ou de baixo. */
export function passoW(c: Conteudo, id: string, passo: number): Conteudo {
  const l = acharW(c, id)
  if (!l) return c
  const col = (c.itens[l.s] as Secao).itens[l.c]
  const t = l.i + passo
  if (t >= 0 && t < col.length) return moverW(c, id, { tipo: 'col', sid: c.itens[l.s].id, c: l.c, i: passo > 0 ? t + 1 : t })
  for (let k = l.s + passo; k >= 0 && k < c.itens.length; k += passo) {
    const o = c.itens[k]
    if (o.tipo !== 'secao') continue
    const ci = passo < 0 ? o.itens.length - 1 : 0
    return moverW(c, id, { tipo: 'col', sid: o.id, c: ci, i: passo < 0 ? o.itens[ci].length : 0 })
  }
  return c
}

/** Passa o elemento para a coluna do lado (no fim dela). */
export function colunaW(c: Conteudo, id: string, passo: number): Conteudo {
  const l = acharW(c, id)
  if (!l) return c
  const sc = c.itens[l.s] as Secao
  const t = l.c + passo
  if (t < 0 || t >= sc.itens.length) return c
  return moverW(c, id, { tipo: 'col', sid: sc.id, c: t, i: sc.itens[t].length })
}

export function duplicarW(c: Conteudo, id: string): [Conteudo, string] {
  const l = acharW(c, id)
  if (!l) return [c, id]
  const sc = c.itens[l.s] as Secao
  const w = sc.itens[l.c][l.i]
  const novo: W = { ...JSON.parse(JSON.stringify(w)), id: novoId() }
  return [porW(c, novo, { tipo: 'col', sid: sc.id, c: l.c, i: l.i + 1 }), novo.id]
}

export function duplicarS(c: Conteudo, id: string): [Conteudo, string] {
  const s = acharS(c, id)
  const o = c.itens[s]
  if (!o || o.tipo !== 'secao') return [c, id]
  const n = copia(c)
  const nova: Secao = { ...o, id: novoId(), itens: o.itens.map(col => col.map(w => ({ ...JSON.parse(JSON.stringify(w)), id: novoId() }))) }
  n.itens.splice(s + 1, 0, nova)
  return [n, nova.id]
}

export function porSecao(c: Conteudo, sc: Secao, i: number): Conteudo {
  const n = copia(c)
  n.itens.splice(Math.max(0, Math.min(i, n.itens.length)), 0, sc)
  return n
}

/** Tudo na ordem da página (seção, os elementos dela coluna a coluna, a próxima seção…): as setas andam nesta ordem. */
export function ordem(c: Conteudo): NonNullable<Sel>[] {
  const out: NonNullable<Sel>[] = []
  for (const it of c.itens) {
    out.push({ tipo: 's', id: it.id })
    if (it.tipo === 'secao') for (const col of it.itens) for (const w of col) out.push({ tipo: 'w', id: w.id })
  }
  return out
}

export function existe(c: Conteudo, sel: Sel): boolean {
  if (!sel) return false
  return sel.tipo === 'w' ? !!acharW(c, sel.id) : acharS(c, sel.id) >= 0
}

const semTags = (h: string) => h.replace(/<[^>]+>/g, ' ').replace(/&nbsp;/g, ' ').replace(/\s+/g, ' ').trim()

/** Uma linha que diz o que o elemento é (Camadas e avisos de leitor de tela). */
export function resumo(w: W): string {
  switch (w.tipo) {
    case 'titulo': return `H${w.nivel} · ${w.texto || tr("vazio")}`
    case 'texto': return semTags(w.html || '').slice(0, 60) || tr("vazio")
    case 'botao': return w.texto || tr("vazio")
    case 'imagem': return w.src ? (w.alt || tr("sem descrição")) : tr("esperando a foto")
    case 'lista': return tr("{0} itens", (w.itens || []).length)
    case 'faq': return tr("{0} perguntas", (w.itens || []).length)
    case 'cartoes': return w.pagina || ''
    case 'produtos': return `${w.quantos} · ${w.categoria || tr("todas")}`
    default: return ''
  }
}

export const NOMES_FUNDO: Record<string, string> = { clara: tr("Claro"), escura: tr("Escuro"), marca: tr("Vermelho"), cinza: tr("Cinza") }

/** O nome do que está selecionado, para a barra, as Camadas e o aviso de leitor de tela. */
export function nomeDe(c: Conteudo, sel: Sel, originais: string[]): string {
  if (!sel) return ''
  if (sel.tipo === 'w') {
    const w = widget(c, sel.id)
    return w ? NOMES[w.tipo] : ''
  }
  const s = acharS(c, sel.id)
  const it = c.itens[s]
  if (!it) return ''
  if (it.tipo === 'original') return tr("Faixa original {0}", it.indice + 1) + (originais[it.indice] ? ` · ${originais[it.indice]}` : '')
  return tr("Seção {0}", c.itens.slice(0, s + 1).filter(x => x.tipo === 'secao').length)
}

/** Onde um elemento está, em palavras ("seção 2, coluna 1, 3º"), para o aviso de leitor de tela. */
export function ondeEsta(c: Conteudo, id: string): string {
  const l = acharW(c, id)
  if (!l) return ''
  const n = c.itens.slice(0, l.s + 1).filter(x => x.tipo === 'secao').length
  const sc = c.itens[l.s] as Secao
  return sc.colunas > 1 ? tr("seção {0}, coluna {1}, posição {2}", n, l.c + 1, l.i + 1) : tr("seção {0}, posição {1}", n, l.i + 1)
}


