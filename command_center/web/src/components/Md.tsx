/* Markdown leve para as respostas da IA: títulos, negrito, itálico, código, listas, parágrafos. Sem HTML cru. */
import { Fragment, type ReactNode } from 'react'

function inline(t: string): ReactNode[] {
  const out: ReactNode[] = []
  const re = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*]+\*)/g
  let last = 0, m: RegExpExecArray | null, k = 0
  while ((m = re.exec(t))) {
    if (m.index > last) out.push(t.slice(last, m.index))
    const s = m[0]
    if (s.startsWith('**')) out.push(<b key={k++}>{s.slice(2, -2)}</b>)
    else if (s.startsWith('`')) out.push(<code key={k++} className="mono" style={{ fontSize: '0.92em' }}>{s.slice(1, -1)}</code>)
    else out.push(<i key={k++}>{s.slice(1, -1)}</i>)
    last = m.index + s.length
  }
  if (last < t.length) out.push(t.slice(last))
  return out
}

export function Md({ text }: { text: string }) {
  const blocks: ReactNode[] = []
  const lines = text.replace(/\r/g, '').split('\n')
  let i = 0, k = 0
  while (i < lines.length) {
    const l = lines[i]
    if (!l.trim()) { i++; continue }
    if (/^ACAO:/i.test(l.trim())) { i++; continue }                      // o protocolo vira cartão de ação, não texto
    const h = /^(#{1,3})\s+(.*)$/.exec(l)
    if (h) { blocks.push(<div key={k++} className="cond" style={{ fontWeight: 700, marginTop: 8 }}>{inline(h[2])}</div>); i++; continue }
    if (/^\s*([-*•]|\d+[.)])\s+/.test(l)) {
      const items: string[] = []
      while (i < lines.length && /^\s*([-*•]|\d+[.)])\s+/.test(lines[i])) { items.push(lines[i].replace(/^\s*([-*•]|\d+[.)])\s+/, '')); i++ }
      const ordered = /^\s*\d/.test(l)
      blocks.push(ordered ? <ol key={k++} style={{ margin: '4px 0', paddingLeft: 22 }}>{items.map((it, j) => <li key={j}>{inline(it)}</li>)}</ol>
        : <ul key={k++} style={{ margin: '4px 0', paddingLeft: 20 }}>{items.map((it, j) => <li key={j}>{inline(it)}</li>)}</ul>)
      continue
    }
    const para: string[] = []
    while (i < lines.length && lines[i].trim() && !/^(#{1,3})\s+/.test(lines[i]) && !/^\s*([-*•]|\d+[.)])\s+/.test(lines[i]) && !/^ACAO:/i.test(lines[i].trim())) { para.push(lines[i]); i++ }
    blocks.push(<p key={k++} style={{ margin: '4px 0' }}>{para.map((pl, j) => <Fragment key={j}>{inline(pl)}{j < para.length - 1 && <br />}</Fragment>)}</p>)
  }
  return <div>{blocks}</div>
}
