/* #313 · o cartão do padrão D (dono, 16/10: "perfeito siga com a opção D"), o mesmo em todo o painel.
 *
 * De cima para baixo, centrado: a pílula da situação, o avatar (as iniciais ou a foto), o nome com a linha de baixo,
 * o bloco grande (a data, o valor ou o número principal), a barra de progresso e a lista do que já aconteceu (cada
 * linha com a ação dela, quando tem), e as ações embaixo, em grade de dois. Cada parte só aparece quando a tela tem o
 * dado: o cartão nunca inventa um campo (NO FAKE DATA).
 *
 * As classes (`.cd`, `.cd-pill`, `.cd-av`, `.cd-quem`, `.cd-nome`, `.cd-sub`, `.cd-bloco`, `.cd-grande`, `.cd-mono`,
 * `.cd-prog`, `.cd-lista`, `.cd-ic`, `.cd-acoes`) estão em `styles/glass.css`, seção #313. */
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import './Cartao.css'

export type TomD = 'ok' | 'warn' | 'crit' | 'info' | 'neutral'

/** As iniciais do nome: "Marina Costa" → "MC"; sem nome, "#". */
export function iniciais(nome?: string | null) {
  const p = (nome || '').replace(/[^\p{L}\p{N}\s]/gu, ' ').trim().split(/\s+/).filter(Boolean)
  return ((p[0]?.[0] || '') + (p.length > 1 ? p[p.length - 1][0] : '')).toUpperCase() || '#'
}

export interface CartaoProps {
  /** o id do título (o cartão é um `article` com aria-labelledby nele) */
  id: string
  /** a pílula da situação, em cima; sem ela, o cartão começa pelo avatar */
  estado?: ReactNode
  tom?: TomD
  /** o avatar: um texto vira iniciais; um elemento (a foto) vai como está; `null`, sem avatar */
  avatar?: string | ReactNode | null
  /** a capa no lugar do avatar (a foto do artigo, quadrada): vai como está, sem o círculo */
  capa?: ReactNode
  /** a cor do avatar: o vermelho da marca (padrão) ou o azul (conta, fornecedor, sistema) */
  avatarTom?: 'marca' | 'azul' | 'neutro'
  nome: ReactNode
  /** h2 quando o cartão está direto sob o h1 da tela; h3 dentro de uma seção; h4 dentro de um cartão */
  nivel?: 2 | 3 | 4
  /** as linhas de baixo do nome (as vazias somem) */
  sub?: ReactNode[]
  /** o bloco grande: o número principal e a linha de baixo dele (só a linha de baixo, quando não há número) */
  grande?: ReactNode
  detalhe?: ReactNode
  /** a barra: só com o dado de verdade (feito de total) */
  progresso?: { feito: number; total: number; rotulo: ReactNode; tom?: TomD } | null
  /** o corpo: a lista (`CdLista`), um formulário (`.cd-form`) ou um aviso */
  children?: ReactNode
  /** os botões de baixo; um só ocupa a linha inteira, e o terceiro também */
  acoes?: ReactNode
  /** a versão compacta, para quadro e prateleira */
  mini?: boolean
  className?: string
  /** atributos `data-*` do cartão (o teste e2e acha o cartão por eles) */
  dados?: Record<`data-${string}`, string | number>
  /** o cartão inteiro abre isto, um caminho ou uma função (o nome vira o link e cobre o cartão; os botões continuam por cima) */
  abrir?: string | (() => void)
}

export function Cartao({ id, estado, tom = 'neutral', avatar, capa, avatarTom = 'marca', nome, nivel = 3, sub, grande, detalhe, progresso, children,
  acoes, mini, className, abrir, dados }: CartaoProps) {
  const H = nivel === 2 ? 'h2' : nivel === 4 ? 'h4' : 'h3'
  const linhas = (sub || []).filter(x => x !== null && x !== undefined && x !== false && x !== '')
  const temGrande = grande !== undefined && grande !== null && grande !== false && grande !== ''
  const temAvatar = avatar !== null && avatar !== undefined && avatar !== false && avatar !== ''
  return <article className={`cd${mini ? ' cd-mini' : ''}${abrir ? ' cd-abre' : ''}${className ? ` ${className}` : ''}`} aria-labelledby={id} {...dados}>
    {estado ? <span className={`cd-pill ${tom}`}>{estado}</span> : null}
    {capa}
    {!capa && temAvatar && <div className={`cd-av${avatarTom === 'marca' ? '' : ` ${avatarTom}`}${typeof avatar === 'string' ? '' : ' foto'}`} aria-hidden="true">
      {typeof avatar === 'string' ? iniciais(avatar) : avatar}</div>}
    <div className="cd-quem">
      <H id={id} className="cd-nome">{typeof abrir === 'string' ? <Link className="cd-link" to={abrir}>{nome}</Link>
        : abrir ? <button type="button" className="cd-link" onClick={abrir}>{nome}</button> : nome}</H>
      {linhas.map((l, i) => <span key={i} className="cd-sub">{l}</span>)}
    </div>
    {(temGrande || detalhe) && <div className="cd-bloco">
      {temGrande && <span className="cd-grande">{grande}</span>}
      {detalhe ? <span className="cd-mono">{detalhe}</span> : null}
    </div>}
    {progresso && progresso.total > 0 && <CdProgresso {...progresso} />}
    {children}
    {acoes ? <div className="cd-acoes">{acoes}</div> : null}
  </article>
}

/** A barra de progresso do cartão: "Pronto para aceitar · 3 de 4". */
export function CdProgresso({ feito, total, rotulo, tom = 'ok' }: { feito: number; total: number; rotulo: ReactNode; tom?: TomD }) {
  const k = Math.max(0, Math.min(1, total ? feito / total : 0))
  return <div className="cd-prog">
    <div className="cd-prog-t"><span>{rotulo}</span><b>{feito}/{total}</b></div>
    <div className={`cd-prog-b ${tom}`} role="progressbar" aria-label={typeof rotulo === 'string' ? rotulo : undefined}
      aria-valuemin={0} aria-valuemax={total} aria-valuenow={feito}>
      <i style={{ transform: `scaleX(${k})` }} /></div>
  </div>
}

/** A lista do cartão. */
export function CdLista({ children }: { children: ReactNode }) {
  return <ul className="cd-lista">{children}</ul>
}

const GLIFO: Record<TomD, string> = { ok: '✓', warn: '!', crit: '✕', info: 'i', neutral: '·' }

/** Uma linha da lista: o ícone da situação, o texto, o valor à direita (ou a ação na linha). */
export function CdItem({ tom = 'neutral', glifo, children, valor, acao }: { tom?: TomD; glifo?: string; children: ReactNode; valor?: ReactNode; acao?: ReactNode }) {
  return <li>
    <i className={`cd-ic ${tom}`} aria-hidden="true">{glifo ?? GLIFO[tom]}</i>
    <span className="grow">{children}</span>
    {valor !== undefined && valor !== null && valor !== '' ? <span className="muted">{valor}</span> : null}
    {acao}
  </li>
}
