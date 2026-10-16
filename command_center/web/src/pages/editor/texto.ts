/* Editor do site como o Canva (#315): o texto escrito no lugar, na prévia. O colar e o texto formatado passam por
 * uma limpeza aqui (as mesmas tags que o servidor aceita em vitrine/html_seguro.py); quem decide no fim é o servidor. */

const PERMITIDAS = new Set(['P', 'BR', 'STRONG', 'B', 'EM', 'I', 'U', 'UL', 'OL', 'LI', 'H2', 'H3', 'H4', 'A'])
const SOMEM = new Set(['SCRIPT', 'STYLE', 'IFRAME', 'OBJECT', 'EMBED', 'TEMPLATE', 'SVG', 'MATH', 'NOSCRIPT', 'HEAD', 'TITLE', 'META', 'LINK'])

/** O mesmo que `link_ok` do servidor: caminho do site, https, tel: ou mailto:. */
export function linkOk(v: string): string | null {
  const t = (v || '').trim()
  if (/^\/[A-Za-z0-9/_\-.?=&%#]*$/.test(t) || /^https:\/\/[^\s"'<>]+$/.test(t)
      || /^(tel:\+?[0-9 ()-]{6,20}|mailto:[^\s"'<>@]+@[^\s"'<>]+)$/.test(t)) return t.slice(0, 300)
  return null
}

/** HTML qualquer (o colado, o do contenteditable) → só as tags do texto do site. `<div>` vira parágrafo. Usa um
 *  documento à parte (DOMParser): nada roda nem carrega enquanto limpa. */
export function limparHtml(html: string): string {
  const fonte = new DOMParser().parseFromString(`<body>${html}</body>`, 'text/html').body
  const saida = document.implementation.createHTMLDocument('')
  const raiz = saida.createElement('div')
  const copiar = (de: Node, para: Element) => {
    de.childNodes.forEach(n => {
      if (n.nodeType === 3) { para.appendChild(saida.createTextNode(n.textContent || '')); return }
      if (n.nodeType !== 1) return
      const el = n as Element
      const tag = el.tagName === 'DIV' ? 'P' : el.tagName
      if (SOMEM.has(tag)) return
      if (!PERMITIDAS.has(tag)) { copiar(el, para); return }       // tag de fora: fica o texto dela
      if (tag === 'A') {
        const href = linkOk(el.getAttribute('href') || '')
        if (!href) { copiar(el, para); return }
        const a = saida.createElement('a')
        a.setAttribute('href', href)
        copiar(el, a)
        para.appendChild(a)
        return
      }
      const novo = saida.createElement(tag.toLowerCase())
      if (tag !== 'BR') copiar(el, novo)
      para.appendChild(novo)
    })
  }
  copiar(fonte, raiz)
  return raiz.innerHTML.trim()
}

/** Texto de uma linha: espaços juntos, sem quebra. */
export const umaLinha = (s: string | null | undefined) => (s || '').replace(/\s+/g, ' ').trim()

/** As linhas de um bloco (os itens da lista enquanto se escreve neles). */
export function linhas(el: HTMLElement): string[] {
  return (el.innerText || '').split('\n').map(umaLinha).filter(Boolean)
}
