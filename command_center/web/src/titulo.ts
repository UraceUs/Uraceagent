/* Título da aba por tela (issue #18): "Compras · URACE Command Center".
 * Um mecanismo só para todas as telas: o título é o h1 da tela (cada tela tem exatamente
 * um — o teste end-to-end garante). Tela com nome dinâmico (o card do cliente) ganha o
 * nome do piloto na aba sem código a mais. */
const SUFIXO = 'URACE Command Center'

function textoDoH1(h: Element) {
  const c = h.cloneNode(true) as Element
  c.querySelectorAll('button, [aria-hidden="true"]').forEach(b => b.remove())
  return (c.textContent || '').replace(/\s+/g, ' ').trim()
}

export function iniciarTituloAutomatico() {
  let pendente = 0
  const atualizar = () => {
    pendente = 0
    const h = document.querySelector('h1')
    const t = h ? textoDoH1(h) : ''
    const novo = t ? `${t.slice(0, 60)} · ${SUFIXO}` : SUFIXO
    if (document.title !== novo) document.title = novo
  }
  new MutationObserver(() => { if (!pendente) pendente = window.setTimeout(atualizar, 50) })
    .observe(document.getElementById('root') || document.body, { childList: true, subtree: true, characterData: true })
  atualizar()
}
