/* O editor de texto simples do painel (#298, #300): negrito, itálico, lista, subtítulo e parágrafo. O servidor
 * guarda só as tags seguras (vitrine/html_seguro.py).
 * #172 (o blog): duas opções a mais, desligadas por padrão para os produtos e o editor do site não mudarem:
 * `link` (pôr e tirar link) e `imagem` (sobe a foto e põe no lugar do cursor, com a descrição). */
import { useEffect, useRef } from 'react'
import { usePerguntar } from './Perguntar'
import { useToast } from './Toast'
import { tr } from '../i18n'

const LINK_OK = /^(https?:\/\/|\/|mailto:|tel:)\S+$/
const attr = (s: string) => s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;')

/** Um editor de texto simples (negrito, itálico, lista, subtítulo). O servidor guarda só as tags seguras. */
export function EditorTexto({ id, rotulo, valor, onChange, disabled, link, imagem }: {
  id: string; rotulo: string; valor: string; onChange: (h: string) => void; disabled?: boolean
  /** #172: botões "Link" e "Tirar link" */
  link?: boolean
  /** #172: botão "Imagem": sobe o arquivo e devolve o endereço da foto (null: não subiu) */
  imagem?: (f: File) => Promise<string | null>
}) {
  const ref = useRef<HTMLDivElement>(null)
  const arquivo = useRef<HTMLInputElement>(null)
  const marcada = useRef<Range | null>(null)
  const perguntar = usePerguntar()
  const toast = useToast()
  useEffect(() => { if (ref.current && ref.current.innerHTML !== valor) ref.current.innerHTML = valor }, [valor])
  const fazer = (cmd: string, arg?: string) => {
    ref.current?.focus()
    document.execCommand(cmd, false, arg)
    if (ref.current) onChange(ref.current.innerHTML)
  }
  // a pergunta (um modal) tira o foco do texto: guarda onde o cursor estava e volta para lá depois
  const guardar = () => {
    const s = window.getSelection()
    marcada.current = s && s.rangeCount && ref.current?.contains(s.anchorNode) ? s.getRangeAt(0).cloneRange() : null
  }
  const voltar = () => {
    ref.current?.focus()
    const s = window.getSelection()
    if (s && marcada.current) { s.removeAllRanges(); s.addRange(marcada.current) }
  }
  async function porLink() {
    guardar()
    const r = await perguntar({ titulo: tr("Link"), campo: tr("Endereço (https://… ou /pagina-do-site/)"), ok: tr("Pôr o link") })
    if (typeof r !== 'string' || !r.trim()) return
    const url = r.trim()
    if (!LINK_OK.test(url)) { toast(tr("Use um endereço que comece com https://, / (uma página do site), mailto: ou tel:"), 'warn'); return }
    voltar()
    if (!marcada.current || marcada.current.collapsed) fazer('insertHTML', `<a href="${attr(url)}">${attr(url)}</a>`)
    else fazer('createLink', url)
  }
  function escolherImagem() { guardar(); arquivo.current?.click() }
  async function porImagem(f: File | undefined) {
    if (!f || !imagem) return
    const src = await imagem(f)
    if (!src) return
    const alt = await perguntar({ titulo: tr("Descrição da foto"), campo: tr("O que a foto mostra (quem não vê a foto ouve este texto)"), ok: tr("Pôr a foto") })
    if (typeof alt !== 'string') return
    voltar()
    fazer('insertHTML', `<img src="${attr(src)}" alt="${attr(alt.trim())}">`)
  }
  const B = 'btn sm ghost'
  const semFoco = (e: { preventDefault: () => void }) => e.preventDefault()
  return <div className="fld" style={{ gridColumn: '1 / -1' }}>
    <span id={`${id}-r`}>{rotulo}</span>
    {!disabled && <div className="editor-barra" role="toolbar" aria-label={tr("Formatar {0}", rotulo)}>
      <button type="button" className={B} onMouseDown={semFoco} onClick={() => fazer('bold')}><b>B</b> <span className="sr-only">{tr("Negrito")}</span></button>
      <button type="button" className={B} onMouseDown={semFoco} onClick={() => fazer('italic')}><i>I</i> <span className="sr-only">{tr("Itálico")}</span></button>
      <button type="button" className={B} onMouseDown={semFoco} onClick={() => fazer('insertUnorderedList')}>{tr("• Lista")}</button>
      <button type="button" className={B} onMouseDown={semFoco} onClick={() => fazer('formatBlock', 'h3')}>{tr("Subtítulo")}</button>
      <button type="button" className={B} onMouseDown={semFoco} onClick={() => fazer('formatBlock', 'p')}>{tr("Parágrafo")}</button>
      {link && <>
        <button type="button" className={B} onMouseDown={semFoco} onClick={porLink}>{tr("Link")}</button>
        <button type="button" className={B} onMouseDown={semFoco} onClick={() => fazer('unlink')}>{tr("Tirar link")}</button></>}
      {imagem && <>
        <button type="button" className={B} onMouseDown={semFoco} onClick={escolherImagem}>{tr("Imagem")}</button>
        <input ref={arquivo} type="file" accept="image/*" className="sr-only" tabIndex={-1} aria-hidden="true"
          onChange={e => { porImagem(e.target.files?.[0]); e.target.value = '' }} /></>}
    </div>}
    <div ref={ref} id={id} className="editor-texto" role="textbox" aria-multiline="true" aria-labelledby={`${id}-r`}
      contentEditable={!disabled} suppressContentEditableWarning onInput={e => onChange((e.target as HTMLDivElement).innerHTML)} />
  </div>
}
