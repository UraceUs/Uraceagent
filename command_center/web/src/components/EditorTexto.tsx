/* O editor de texto simples do painel (#298, #300): negrito, itálico, lista, subtítulo e parágrafo. O servidor
 * guarda só as tags seguras (vitrine/html_seguro.py). */
import { useEffect, useRef } from 'react'
import { tr } from '../i18n'

/** Um editor de texto simples (negrito, itálico, lista, subtítulo). O servidor guarda só as tags seguras. */
export function EditorTexto({ id, rotulo, valor, onChange, disabled }: { id: string; rotulo: string; valor: string; onChange: (h: string) => void; disabled?: boolean }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => { if (ref.current && ref.current.innerHTML !== valor) ref.current.innerHTML = valor }, [valor])
  const fazer = (cmd: string, arg?: string) => {
    ref.current?.focus()
    document.execCommand(cmd, false, arg)
    if (ref.current) onChange(ref.current.innerHTML)
  }
  return <div className="fld" style={{ gridColumn: '1 / -1' }}>
    <span id={`${id}-r`}>{rotulo}</span>
    {!disabled && <div className="editor-barra" role="toolbar" aria-label={tr("Formatar {0}", rotulo)}>
      <button type="button" className="btn sm ghost" onMouseDown={e => e.preventDefault()} onClick={() => fazer('bold')}><b>B</b> <span className="sr-only">{tr("Negrito")}</span></button>
      <button type="button" className="btn sm ghost" onMouseDown={e => e.preventDefault()} onClick={() => fazer('italic')}><i>I</i> <span className="sr-only">{tr("Itálico")}</span></button>
      <button type="button" className="btn sm ghost" onMouseDown={e => e.preventDefault()} onClick={() => fazer('insertUnorderedList')}>{tr("• Lista")}</button>
      <button type="button" className="btn sm ghost" onMouseDown={e => e.preventDefault()} onClick={() => fazer('formatBlock', 'h3')}>{tr("Subtítulo")}</button>
      <button type="button" className="btn sm ghost" onMouseDown={e => e.preventDefault()} onClick={() => fazer('formatBlock', 'p')}>{tr("Parágrafo")}</button>
    </div>}
    <div ref={ref} id={id} className="editor-texto" role="textbox" aria-multiline="true" aria-labelledby={`${id}-r`}
      contentEditable={!disabled} suppressContentEditableWarning onInput={e => onChange((e.target as HTMLDivElement).innerHTML)} />
  </div>
}

