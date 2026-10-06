/* O PDF da waiver na tela, página por página (#107).
 *
 * A Flórida exige que o aviso da waiver de menor (§744.301(3)) apareça em maiúsculas e maior que o
 * resto: o texto extraído perdia isso. Aqui é o próprio PDF, desenhado com o pdf.js (build legacy,
 * para iPhone antigo), carregado só nesta rota e sem WebAssembly, que a CSP do painel não libera.
 * Cada página que passa pela tela (metade dela visível, ou tudo o que cabe na caixa) conta como
 * vista; quando todas foram vistas, `onLido` recebe a hora. Se o pdf.js falhar, `onFalha` avisa e
 * a tela cai para o texto. */
import { useEffect, useRef, useState } from 'react'

export function VisorPdf({ url, onLido, onFalha }: { url: string; onLido: (quando: string) => void; onFalha: () => void }) {
  const caixa = useRef<HTMLDivElement>(null)
  const folhas = useRef<HTMLDivElement>(null)
  const [total, setTotal] = useState(0)
  const [vistas, setVistas] = useState(0)
  const avisou = useRef(false)
  const lido = useRef(onLido)
  const falha = useRef(onFalha)
  useEffect(() => { lido.current = onLido; falha.current = onFalha })

  useEffect(() => {
    const alvo = folhas.current
    let vivo = true
    let destruir: (() => void) | null = null
    let obs: IntersectionObserver | null = null
    const vistasSet = new Set<number>()
    ;(async () => {
      try {
        const pdfjs = await import('pdfjs-dist/legacy/build/pdf.mjs')
        const { default: worker } = await import('pdfjs-dist/legacy/build/pdf.worker.min.mjs?url')
        pdfjs.GlobalWorkerOptions.workerSrc = worker
        const tarefa = pdfjs.getDocument({ url, useWasm: false, withCredentials: true })
        destruir = () => { void tarefa.destroy() }
        const doc = await tarefa.promise
        if (!vivo || !caixa.current || !folhas.current) return
        setTotal(doc.numPages)
        const raiz = caixa.current
        obs = new IntersectionObserver(entradas => {
          for (const e of entradas) {
            const n = Number((e.target as HTMLElement).dataset.pagina)
            const cabe = e.intersectionRect.height >= raiz.clientHeight * 0.8
            if (e.isIntersecting && (e.intersectionRatio >= 0.5 || cabe) && !vistasSet.has(n)) {
              vistasSet.add(n); setVistas(vistasSet.size)
              if (vistasSet.size === doc.numPages && !avisou.current) { avisou.current = true; lido.current(new Date().toISOString()) }
            }
          }
        }, { root: raiz, threshold: [0, 0.25, 0.5, 0.75, 1] })
        const largura = Math.max(240, folhas.current.clientWidth)
        const dpr = Math.min(window.devicePixelRatio || 1, 2)
        for (let n = 1; n <= doc.numPages; n++) {
          const pg = await doc.getPage(n)
          if (!vivo) return
          const base = pg.getViewport({ scale: 1 })
          const vp = pg.getViewport({ scale: (largura / base.width) * dpr })
          const folha = document.createElement('figure')
          folha.className = 'pdf-folha'
          folha.dataset.pagina = String(n)
          const tela = document.createElement('canvas')
          tela.width = Math.floor(vp.width); tela.height = Math.floor(vp.height)
          tela.setAttribute('role', 'img')
          tela.setAttribute('aria-label', `Waiver document, page ${n} of ${doc.numPages}`)
          const legenda = document.createElement('figcaption')
          legenda.textContent = `Page ${n} of ${doc.numPages}`
          folha.append(tela, legenda)
          folhas.current.append(folha)
          await pg.render({ canvas: tela, viewport: vp }).promise
          obs.observe(folha)
        }
      } catch {
        if (vivo) falha.current()
      }
    })()
    return () => { vivo = false; obs?.disconnect(); destruir?.(); alvo?.replaceChildren() }
  }, [url])

  return <div className="stack" style={{ gap: 6 }}>
    <div ref={caixa} className="card pdf-caixa" tabIndex={0} aria-label="Waiver document">
      {!total && <div className="state"><span className="spin" /></div>}
      <div ref={folhas} />
    </div>
    <div className="small muted" aria-live="polite">{total === 0 ? 'Loading the document…'
      : vistas < total ? `Scroll through every page to continue: ${vistas} of ${total} read.` : `All ${total} page${total > 1 ? 's' : ''} read.`}</div>
  </div>
}
