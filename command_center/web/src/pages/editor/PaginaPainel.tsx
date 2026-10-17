/* Editor do site como o Canva (#315): a página em si, fora da prévia. O título da aba e a descrição (o que o
 * Google mostra), o endereço, o que falta para publicar, Voltar ao original / Tirar do ar e as versões. */
import { fmtDateTime } from '../../components/fmt'
import { tr } from '../../i18n'
import type { Pagina, Seo } from './tipos'

export interface Versao { id: number; title: string; published_at: string; por: string | null }

interface Props {
  p: Pagina
  seo: Seo
  gerente: boolean
  problemas: string[]
  erros: string[]
  mudarSeo(x: Partial<Seo>): void
  despublicar(): void
  versoes: Versao[] | null
  abrirVersoes(): void
  voltarVersao(id: number): void
  recarregar(): void
}

export function PaginaPainel({ p, seo, gerente, problemas, erros, mudarSeo, despublicar, versoes, abrirVersoes, voltarVersao, recarregar }: Props) {
  return <div className="stack" style={{ gap: 12 }}>
    <label className="fld"><span>{tr("Título da aba")} <i>{tr("10 a 70 letras; o Google mostra")}</i></span>
      <input value={seo.title} disabled={!gerente} onChange={e => mudarSeo({ title: e.target.value })} /></label>
    <label className="fld"><span>{tr("Descrição")} <i>{tr("50 a 170 letras; o texto do Google embaixo do título")}</i></span>
      <textarea rows={3} value={seo.description} disabled={!gerente} onChange={e => mudarSeo({ description: e.target.value })} /></label>
    <label className="fld"><span>{tr("Endereço")} {(p.base || p.published) && <i>{tr("não muda depois de publicada")}</i>}</span>
      <input value={seo.path} disabled={!gerente || !!p.base || !!p.published} onChange={e => mudarSeo({ path: e.target.value })} /></label>
    {(problemas.length > 0 || erros.length > 0) && <div className="ed-problemas" role="status"><b>{tr("Antes de publicar:")}</b><ul>
      {erros.map(x => <li key={'e' + x}>{x}</li>)}{problemas.map(x => <li key={x}>{x}</li>)}</ul></div>}
    {gerente && <div className="row wrap" style={{ gap: 8 }}>
      {p.published && <button type="button" className="btn ghost" onClick={despublicar}>{p.base ? tr("Voltar ao original") : tr("Tirar do ar")}</button>}
      {p.published && <a className="btn ghost" href={p.path} target="_blank" rel="noreferrer">{tr("Ver no site ↗")}</a>}
      <button type="button" className="btn ghost" onClick={recarregar}>{tr("Recarregar a prévia")}</button>
    </div>}
    <div className="stack" style={{ gap: 6 }}>
      <h3 className="h3" style={{ margin: 0 }}>{tr("Versões publicadas")}</h3>
      {versoes === null ? <div><button type="button" className="btn sm ghost" onClick={abrirVersoes}>{tr("Ver as versões")}</button></div>
        : !versoes.length ? <p className="small muted" style={{ margin: 0 }}>{tr("Ainda não foi publicada.")}</p>
        : versoes.map(x => <div key={x.id} className="row wrap" style={{ gap: 8 }}><span className="small grow">{fmtDateTime(x.published_at)} · {x.por || '—'} · {x.title}</span>
          {gerente && <button type="button" className="btn sm ghost" onClick={() => voltarVersao(x.id)}>{tr("Voltar a esta versão")}</button>}</div>)}
    </div>
    <details className="ed-atalhos"><summary className="btn sm ghost">{tr("Atalhos do teclado")}</summary>
      <ul className="small">
        <li><kbd>Enter</kbd> {tr("escrever no que está selecionado")} · <kbd>Esc</kbd> {tr("sair do texto, depois subir para a seção")}</li>
        <li><kbd>↑</kbd> <kbd>↓</kbd> {tr("o anterior e o próximo")} · <kbd>Alt</kbd>+<kbd>↑</kbd> <kbd>↓</kbd> {tr("mover")} · <kbd>Alt</kbd>+<kbd>←</kbd> <kbd>→</kbd> {tr("mudar de coluna")}</li>
        <li><kbd>Ctrl</kbd>+<kbd>Z</kbd> {tr("desfazer")} · <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>Z</kbd> {tr("refazer")} · <kbd>Ctrl</kbd>+<kbd>D</kbd> {tr("duplicar")} · <kbd>Delete</kbd> {tr("apagar")}</li>
        <li><kbd>Ctrl</kbd>+<kbd>B</kbd> <kbd>I</kbd> <kbd>K</kbd> {tr("negrito, itálico e link no texto")} · <kbd>Ctrl</kbd>+<kbd>S</kbd> {tr("salvar já")}</li>
      </ul></details>
  </div>
}
