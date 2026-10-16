/* Editor do site como o Canva (#315): a barra do que está selecionado. Botões e amostras, sem formulário: o texto
 * se escreve na própria prévia. No computador ela flutua em cima da peça; no celular fica presa embaixo.
 * Só o link do botão, o link do texto e a descrição da foto pedem uma linha para escrever (num balão na barra). */
import { useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Icon } from '../../components/Icon'
import { tr } from '../../i18n'
import { DE_ESCREVER, NOMES_FUNDO } from './modelo'
import { linkOk } from './texto'
import type { Faq, Item, Secao, W } from './tipos'

export interface AcoesBarra {
  mudarW(x: Partial<W>, chave?: string): void
  mudarS(x: Partial<Secao>): void
  oculto(): void
  passo(p: number): void
  coluna(p: number): void
  duplicar(): void
  apagar(): void
  editar(): void
  parar(): void
  comando(cmd: string): void
  linkNoTexto(url: string): void
  trocarFoto(): void
  legenda(): void
  fechar(): void
}

export interface Ancora { top: number; bottom: number; left: number; right: number }

interface Props {
  w: W | null
  it: Item | null
  nome: string
  editando: boolean
  /** A página já tem um h1 (fora este elemento): o H1 fica desligado. */
  h1Ocupado: boolean
  erro?: string
  pode: { cima: boolean; baixo: boolean; esq: boolean; dir: boolean }
  a: AcoesBarra
  estreito: boolean
  ancora: Ancora | null
  limites: { w: number; h: number }
  /** Abre já o balão (a descrição da foto que acabou de subir; Ctrl+K no texto). */
  balao: { qual: Balao; vez: number } | null
}
type Balao = 'link' | 'alt' | 'linkTexto'

const TAM: [string, string, string][] = [['p', 'P', tr("Pequeno")], ['m', 'M', tr("Médio")], ['g', 'G', tr("Grande")]]
const COR: [string, string][] = [['padrao', tr("Cor padrão")], ['marca', tr("Vermelho da marca")], ['suave', tr("Cinza suave")]]
const CATS: [string, string][] = [['', tr("Todas")], ['chassis', 'Chassis'], ['competition-karts', 'Competition karts'], ['engines', 'Engines'],
  ['parts', 'Parts'], ['tires', 'Tires'], ['custom-kart-suits', 'Custom kart suits'], ['official-urace-products', 'Official URACE products'],
  ['kart-driver-training', 'Programs']]
const PG_CARTOES: [string, string][] = [['academy', 'Academy'], ['pro-team', 'Pro Team'], ['for-beginners', 'For Beginners']]

function B({ on, rotulo, onClick, disabled, children, className }: { on?: boolean; rotulo: string; onClick: () => void; disabled?: boolean; children: ReactNode; className?: string }) {
  return <button type="button" className={`btn sm ${on ? 'on' : 'ghost'}${className ? ' ' + className : ''}`} aria-pressed={on === undefined ? undefined : on}
    aria-label={rotulo} title={rotulo} disabled={disabled} onClick={onClick}>{children}</button>
}
const G = ({ children, rotulo }: { children: ReactNode; rotulo: string }) => <div className="ed-grupo" role="group" aria-label={rotulo}>{children}</div>

export function Barra({ w, it, nome, editando, h1Ocupado, erro, pode, a, estreito, ancora, limites, balao }: Props) {
  const ref = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null)
  const [pop, setPop] = useState<Balao | null>(null)
  const [valor, setValor] = useState('')
  const [aviso, setAviso] = useState('')
  // o balão pedido de fora (a foto que acabou de subir pede a descrição; Ctrl+K no texto pede o link)
  const [visto, setVisto] = useState(balao?.vez)
  if (balao && balao.vez !== visto) {
    setVisto(balao.vez); setPop(balao.qual); setAviso('')
    setValor(balao.qual === 'link' ? w?.link || '' : balao.qual === 'alt' ? w?.alt || '' : '')
  }
  useLayoutEffect(() => {
    const el = ref.current
    if (estreito || !el || !ancora) { setPos(null); return }
    const b = el.getBoundingClientRect()
    const W = limites.w || b.width
    const H = limites.h || 600
    let top = ancora.top - b.height - 10
    if (top < 6) top = ancora.bottom + 10
    if (top + b.height > H - 6) top = Math.max(6, Math.min(ancora.top + 6, H - b.height - 6))
    const left = Math.max(6, Math.min(ancora.left, W - b.width - 6))
    setPos(p => p && p.top === top && p.left === left ? p : { top, left })
  }, [ancora, limites, estreito, pop, w, it, editando, erro])

  function abrir(q: Balao) {
    if (pop === q) { setPop(null); return }
    setPop(q); setAviso('')
    setValor(q === 'link' ? w?.link || '' : q === 'alt' ? w?.alt || '' : '')
  }
  function confirmarLink() {
    const ok = linkOk(valor)
    if (!ok) { setAviso(tr("Use um caminho do site (ex.: /contact/), https://, tel: ou mailto:")); return }
    if (pop === 'link') a.mudarW({ link: ok })
    else a.linkNoTexto(ok)
    setPop(null)
  }

  const mover = <G rotulo={tr("Mover")}>
    <B rotulo={tr("Subir")} disabled={!pode.cima} onClick={() => a.passo(-1)}>↑</B>
    <B rotulo={tr("Descer")} disabled={!pode.baixo} onClick={() => a.passo(1)}>↓</B>
    {(pode.esq || pode.dir) && <>
      <B rotulo={tr("Coluna da esquerda")} disabled={!pode.esq} onClick={() => a.coluna(-1)}>←</B>
      <B rotulo={tr("Coluna da direita")} disabled={!pode.dir} onClick={() => a.coluna(1)}>→</B></>}
  </G>
  const comum = <>
    {mover}
    <G rotulo={tr("Mais")}>
      <B rotulo={tr("Duplicar")} onClick={a.duplicar}>{tr("Duplicar")}</B>
      <B rotulo={tr("Apagar")} onClick={a.apagar} className="ed-apagar"><Icon name="trash" size={16} /></B>
    </G>
  </>
  const tamanho = (v: string | undefined, f: (x: string) => void, rot = tr("Tamanho")) => <G rotulo={rot}>
    {TAM.map(([k, curto, longo]) => <B key={k} on={(v || 'm') === k} rotulo={`${rot}: ${longo}`} onClick={() => f(k)}>{curto}</B>)}</G>
  const alinhar = (x: W) => <G rotulo={tr("Alinhamento")}>
    <B on={(x.alinhar || 'esq') === 'esq'} rotulo={tr("À esquerda")} onClick={() => a.mudarW({ alinhar: 'esq' })}>⇤</B>
    <B on={x.alinhar === 'centro'} rotulo={tr("No centro")} onClick={() => a.mudarW({ alinhar: 'centro' })}>↔</B></G>
  const cor = (x: W) => <G rotulo={tr("Cor")}>
    {COR.map(([k, n]) => <button key={k} type="button" className={`ed-amostra ed-am-t-${k}`} aria-pressed={(x.cor || 'padrao') === k} aria-label={n} title={n}
      onClick={() => a.mudarW({ cor: k })} />)}</G>
  const escrever = (x: W) => DE_ESCREVER.includes(x.tipo) && (x.tipo !== 'imagem' || !!x.legenda) && <G rotulo={tr("Texto")}>
    {editando ? <B rotulo={tr("Pronto: sair do texto")} onClick={a.parar}><Icon name="check" size={16} /> {tr("Pronto")}</B>
      : <B rotulo={tr("Escrever no lugar")} onClick={a.editar}><Icon name="pencil" size={16} /> {tr("Escrever")}</B>}</G>

  let miolo: ReactNode = null
  if (w) {
    switch (w.tipo) {
      case 'titulo': miolo = <>
        <G rotulo={tr("Nível do título")}>{[1, 2, 3].map(n => <B key={n} on={w.nivel === n} rotulo={n === 1 ? tr("Nível 1: o título da página (um só)") : n === 2 ? tr("Nível 2: título de seção") : tr("Nível 3: subtítulo")}
          disabled={n === 1 && h1Ocupado && w.nivel !== 1} onClick={() => a.mudarW({ nivel: n })}>H{n}</B>)}</G>
        {escrever(w)}{tamanho(w.tamanho, x => a.mudarW({ tamanho: x }))}{cor(w)}{alinhar(w)}</>; break
      case 'texto': miolo = <>
        {escrever(w)}
        {editando && <G rotulo={tr("Formatar")}>
          <B rotulo={tr("Negrito")} onClick={() => a.comando('bold')}><b>B</b></B>
          <B rotulo={tr("Itálico")} onClick={() => a.comando('italic')}><i>I</i></B>
          <B rotulo={tr("Lista")} onClick={() => a.comando('insertUnorderedList')}>{tr("• Lista")}</B>
          <B on={pop === 'linkTexto'} rotulo={tr("Link (marque o texto antes)")} onClick={() => abrir('linkTexto')}>{tr("Link")}</B></G>}
        {tamanho(w.tamanho, x => a.mudarW({ tamanho: x }))}{cor(w)}{alinhar(w)}</>; break
      case 'botao': miolo = <>
        {escrever(w)}
        <G rotulo={tr("Estilo")}><B on={(w.estilo || 'cheio') === 'cheio'} rotulo={tr("Cheio (vermelho)")} onClick={() => a.mudarW({ estilo: 'cheio' })}>{tr("Cheio")}</B>
          <B on={w.estilo === 'linha'} rotulo={tr("Contorno")} onClick={() => a.mudarW({ estilo: 'linha' })}>{tr("Contorno")}</B></G>
        <G rotulo={tr("Link do botão")}><B on={pop === 'link'} rotulo={tr("Link do botão")} onClick={() => abrir('link')}>{tr("Link")}{w.link ? '' : ' !'}</B></G>
        {alinhar(w)}</>; break
      case 'imagem': miolo = <>
        <G rotulo={tr("Foto")}><B rotulo={tr("Trocar a foto")} onClick={a.trocarFoto}>{w.src ? tr("Trocar foto") : tr("Escolher foto")}</B>
          <B on={pop === 'alt'} rotulo={tr("Descrição da foto")} onClick={() => abrir('alt')} className={w.src && !w.alt ? 'ed-falta' : ''}>{tr("Descrição")}{w.src && !w.alt ? ' !' : ''}</B>
          {!w.legenda && <B rotulo={tr("Pôr legenda")} onClick={a.legenda}>{tr("Legenda")}</B>}</G>
        {escrever(w)}
        <G rotulo={tr("Formato")}>{([['larga', tr("Largura toda")], ['media', tr("Média")], ['quadrada', tr("Quadrada")]] as [string, string][]).map(([k, n]) =>
          <B key={k} on={(w.forma || 'larga') === k} rotulo={n} onClick={() => a.mudarW({ forma: k })}>{n}</B>)}</G></>; break
      case 'lista': miolo = escrever(w); break
      case 'faq': miolo = <>{escrever(w)}
        <G rotulo={tr("Perguntas")}><B rotulo={tr("+ Pergunta")} onClick={() => a.mudarW({ itens: [...((w.itens as Faq[]) || []), { pergunta: 'Question?', resposta: 'Answer.' }] })}>{tr("+ Pergunta")}</B>
          {((w.itens as Faq[]) || []).length > 0 && <B rotulo={tr("Tirar a última pergunta")} onClick={() => a.mudarW({ itens: ((w.itens as Faq[]) || []).slice(0, -1) })}>{tr("− Pergunta")}</B>}</G></>; break
      case 'espaco': miolo = tamanho(w.tamanho, x => a.mudarW({ tamanho: x }), tr("Altura")); break
      case 'karts': miolo = <G rotulo={tr("De onde vem")}><Link className="btn sm ghost" to="/site/servicos">{tr("Vem de Serviços e preços ↗")}</Link></G>; break
      case 'produtos': miolo = <>
        <G rotulo={tr("Categoria")}><select className="ed-escolha" aria-label={tr("Categoria")} value={w.categoria || ''} onChange={e => a.mudarW({ categoria: e.target.value })}>
          {CATS.map(([k, n]) => <option key={k} value={k}>{n}</option>)}</select></G>
        <G rotulo={tr("Quantos")}>{[3, 6, 9, 12].map(n => <B key={n} on={w.quantos === n} rotulo={tr("{0} produtos", n)} onClick={() => a.mudarW({ quantos: n })}>{n}</B>)}</G>
        <G rotulo={tr("De onde vem")}><Link className="btn sm ghost" to="/site/produtos">{tr("Produtos da loja ↗")}</Link></G></>; break
      case 'cartoes': miolo = <>
        <G rotulo={tr("Página dos cartões")}>{PG_CARTOES.map(([k, n]) => <B key={k} on={(w.pagina || 'academy') === k} rotulo={n} onClick={() => a.mudarW({ pagina: k })}>{n}</B>)}</G>
        <G rotulo={tr("De onde vem")}><Link className="btn sm ghost" to="/site/cartoes">{tr("Cartões das páginas ↗")}</Link></G></>; break
    }
  } else if (it?.tipo === 'secao') {
    miolo = <>
      <G rotulo={tr("Fundo")}>{Object.entries(NOMES_FUNDO).map(([k, n]) => <button key={k} type="button" className={`ed-amostra ed-am-f-${k}`} aria-pressed={it.fundo === k}
        aria-label={tr("Fundo: {0}", n)} title={n} onClick={() => a.mudarS({ fundo: k })} />)}</G>
      {tamanho(it.espaco, x => a.mudarS({ espaco: x }), tr("Espaço"))}
      <G rotulo={tr("Colunas")}>{[1, 2, 3].map(n => <B key={n} on={it.colunas === n} rotulo={tr("{0} coluna(s)", n)} onClick={() => a.mudarS({ colunas: n })}>{tr("{0} col.", n)}</B>)}</G>
    </>
  } else if (it?.tipo === 'original') {
    miolo = <G rotulo={tr("Faixa")}><B rotulo={it.oculto ? tr("Mostrar a faixa") : tr("Esconder a faixa")} onClick={a.oculto}>
      <Icon name="eye" size={16} /> {it.oculto ? tr("Mostrar") : tr("Esconder")}</B></G>
  }

  return <div ref={ref} className={`ed-barra${estreito ? ' ed-barra-baixo' : ''}`} role="toolbar" aria-label={tr("Opções: {0}", nome)}
    style={estreito ? undefined : pos ? { top: pos.top, left: pos.left } : { visibility: 'hidden' }}
    onMouseDown={e => { if (!(e.target as Element).closest('input, select')) e.preventDefault() }}>
    {estreito && <B rotulo={tr("Fechar a seleção")} onClick={a.fechar}><Icon name="x" size={16} /></B>}
    <span className="ed-barra-nome">{nome}</span>
    {miolo}
    {(w || it?.tipo === 'secao') ? comum : it ? mover : null}
    {erro && <p className="ed-erro-msg" role="alert">{erro}</p>}
    {pop && w && <div className="ed-pop">
      {pop === 'alt' ? <>
        <label className="fld"><span>{tr("Descrição da foto")} <i>{tr("o que ela mostra, em inglês (quem não vê a foto e o Google leem)")}</i></span>
          <input autoFocus value={w.alt || ''} onChange={e => a.mudarW({ alt: e.target.value }, `alt:${w.id}`)}
            onKeyDown={e => { if (e.key === 'Enter' || e.key === 'Escape') setPop(null) }} /></label>
        <div><button type="button" className="btn sm" onClick={() => setPop(null)}>{tr("Pronto")}</button></div></>
        : <>
          <label className="fld"><span>{pop === 'link' ? tr("Link do botão") : tr("Link do texto marcado")} <i>{tr("ex.: /contact/ ou https://")}</i></span>
            <input autoFocus value={valor} onChange={e => { setValor(e.target.value); setAviso('') }}
              onKeyDown={e => { if (e.key === 'Enter') confirmarLink(); if (e.key === 'Escape') setPop(null) }} /></label>
          {aviso && <p className="ed-erro-msg" role="alert">{aviso}</p>}
          <div className="row" style={{ gap: 6 }}><button type="button" className="btn sm primary" onClick={confirmarLink}>{tr("Usar o link")}</button>
            <button type="button" className="btn sm ghost" onClick={() => setPop(null)}>{tr("Cancelar")}</button></div></>}
    </div>}
  </div>
}
