/* Editor do site como o Canva (#315): a lona, a prévia da página onde se trabalha.
 *
 * Um iframe da mesma origem com a página do site de verdade, desenhada do rascunho (`previa?editar=1`). Em
 * sandbox (sem formulário, janela nova nem navegar o painel). No computador alterna entre 390 px (celular) e
 * 1280 px (computador, reduzido com transform para caber); no celular ocupa a largura toda. */
import { useEffect, useImperativeHandle, useRef, useState, type Ref } from 'react'
import { tr } from '../../i18n'
import { Ponte, type Ganchos } from './ponte'

export interface LonaApi {
  ponte(): Ponte | null
  /** Do ponto da tela do painel (clientX/Y) para o da prévia. */
  paraDentro(x: number, y: number): { x: number; y: number } | null
  /** Do retângulo da prévia para o do painel, relativo à lona. */
  paraFora(r: DOMRect): { top: number; left: number; bottom: number; right: number } | null
  tamanho(): { w: number; h: number }
  recarregar(): void
}

interface Props {
  ref: Ref<LonaApi>
  src: string
  tela: 'celular' | 'computador'
  estreito: boolean
  editar: boolean
  ganchos: () => Ganchos
  dica: (tipo: string) => string
  aoLigar: (p: Ponte) => void
  /** Uma tampa por cima enquanto a paleta arrasta: o painel recebe o ponteiro inteiro. */
  tampa: boolean
}

export function Lona({ ref, src, tela, estreito, editar, ganchos, dica, aoLigar, tampa }: Props) {
  const moldura = useRef<HTMLDivElement>(null)
  const iframe = useRef<HTMLIFrameElement>(null)
  const ponte = useRef<Ponte | null>(null)
  const [vez, setVez] = useState(0)
  const [tam, setTam] = useState({ w: 0, h: 0 })
  useEffect(() => {
    const m = moldura.current
    if (!m) return
    const medir = () => setTam({ w: m.clientWidth, h: m.clientHeight })
    medir()
    const ro = new ResizeObserver(medir)
    ro.observe(m)
    return () => ro.disconnect()
  }, [])
  useEffect(() => () => { ponte.current?.desligar(); ponte.current = null }, [])

  const pc = !estreito && tela === 'computador'
  const largura = estreito ? tam.w : pc ? 1280 : Math.min(390, tam.w || 390)
  const escala = pc && tam.w ? Math.min(1, tam.w / 1280) : 1
  const esquerda = Math.max(0, (tam.w - largura * escala) / 2)

  function ligar() {
    ponte.current?.desligar()
    ponte.current = null
    const doc = iframe.current?.contentDocument
    if (!doc || !doc.getElementById('conteudo')) return
    const p = new Ponte(doc, ganchos, editar, dica)
    p.ligar()
    ponte.current = p
    aoLigar(p)
  }

  useImperativeHandle(ref, () => ({
    ponte: () => ponte.current,
    paraDentro: (x, y) => {
      const f = iframe.current?.getBoundingClientRect()
      return f ? { x: (x - f.left) / escala, y: (y - f.top) / escala } : null
    },
    paraFora: r => {
      const f = iframe.current?.getBoundingClientRect()
      const m = moldura.current?.getBoundingClientRect()
      if (!f || !m) return null
      return { top: f.top - m.top + r.top * escala, left: f.left - m.left + r.left * escala,
        bottom: f.top - m.top + r.bottom * escala, right: f.left - m.left + r.right * escala }
    },
    tamanho: () => tam,
    recarregar: () => { ponte.current?.desligar(); ponte.current = null; setVez(x => x + 1) },
  }), [escala, tam])

  return <div className={`ed-lona${pc ? ' ed-lona-pc' : ''}`} ref={moldura}>
    {tam.w > 0 && <iframe key={vez} ref={iframe} className="ed-iframe" title={tr("Página em edição")} sandbox="allow-same-origin allow-scripts"
      src={`${src}?editar=1${vez ? `&vez=${vez}` : ''}`} onLoad={ligar}
      style={{ width: largura, height: tam.h / escala, left: esquerda, transform: escala < 1 ? `scale(${escala})` : undefined }} />}
    {tampa && <div className="ed-tampa" aria-hidden="true" />}
  </div>
}
