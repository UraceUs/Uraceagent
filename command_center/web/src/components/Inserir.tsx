/* #312 (dono, 16/10): "Se tiver muito serviço, vai acabar que ele vai ficar lá embaixo e a gente não vai ter acesso.
 * Então eu preciso que essas coisas de inserção fiquem sempre por cima, assim que abrir."
 *
 * <InserirNoTopo rotulo="Adicionar serviço"> é o botão de inserir no topo da tela (ou da seção): ele abre, logo
 * abaixo dele, o painel com o formulário, leva o foco ao primeiro campo e mostra o painel na tela. Esc ou "Fechar"
 * fecham e devolvem o foco ao botão. `sempre`: sem botão, o painel fica aberto no topo (inserção de uma linha só,
 * como a anotação da venda). O painel é um cartão do padrão D (`.cd`); `dentro` é a versão sem borda, para quando
 * ele já está dentro de um cartão. O formulário em si é o de sempre: ele vem como `children`. */
import { useEffect, useId, useRef, useState, type ReactNode } from 'react'
import { tr } from '../i18n'

const CAMPO = 'input:not([type=hidden]):not([disabled]), select:not([disabled]), textarea:not([disabled]), button:not([disabled])'

export function InserirNoTopo({ rotulo, titulo, nivel = 2, sempre, dentro, primario, inicial, children }: {
  /** o texto do botão (e o nome do painel) */
  rotulo: string
  /** o título do painel; `false`: sem título (o botão, ou o próprio campo, já diz o que é) */
  titulo?: string | false
  /** h2 numa tela; h3 dentro de uma seção ou de uma janela */
  nivel?: 2 | 3
  sempre?: boolean
  dentro?: boolean
  primario?: boolean
  /** começa aberto (ex.: a lista ainda está vazia) */
  inicial?: boolean
  children: ReactNode
}) {
  const id = useId()
  const [aberto, setAberto] = useState(!!inicial)
  const botao = useRef<HTMLButtonElement>(null)
  const painel = useRef<HTMLElement>(null)
  const [aberturas, setAberturas] = useState(0)        // cada vez que o botão abre: o foco e a rolagem vão junto
  const visivel = sempre || aberto
  const fechar = () => { setAberto(false); requestAnimationFrame(() => botao.current?.focus()) }

  useEffect(() => {
    const p = painel.current
    if (!aberturas || !p) return
    const reduz = typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches
    // o primeiro campo do formulário; sem campo (ex.: falta escolher o motor), o "Fechar"
    ;(p.querySelector('.cd-form')?.querySelector<HTMLElement>(CAMPO) || p.querySelector<HTMLElement>(CAMPO))?.focus({ preventScroll: true })
    p.scrollIntoView?.({ block: 'nearest', behavior: reduz ? 'auto' : 'smooth' })
  }, [aberturas])

  const H = nivel === 3 ? 'h3' : 'h2'
  const nome = titulo === false ? null : (titulo || rotulo)
  return <div className={`ins${sempre ? ' sempre' : ''}`}>
    {!sempre && <div className="ins-barra">
      <button ref={botao} type="button" className={`btn${primario ? ' primary' : ''}`} aria-expanded={aberto} aria-controls={id}
        onClick={() => { if (aberto) fechar(); else { setAberto(true); setAberturas(n => n + 1) } }}>
        <span aria-hidden="true">{aberto ? '−' : '+'}</span> {rotulo}</button>
    </div>}
    {visivel && <section ref={painel} id={id} className={`cd ins-painel${dentro ? ' dentro' : ''}`} aria-label={nome ? undefined : rotulo}
      aria-labelledby={nome ? `${id}-t` : undefined}
      onKeyDown={e => { if (!sempre && e.key === 'Escape') { e.stopPropagation(); fechar() } }}>
      {nome && <div className="cd-quem"><H id={`${id}-t`} className="cd-nome">{nome}</H></div>}
      <div className="cd-form">{children}</div>
      {!sempre && <div className="cd-acoes um"><button type="button" className="btn ghost" onClick={fechar}>{tr("Fechar")}</button></div>}
    </section>}
  </div>
}
