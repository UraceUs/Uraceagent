/* Confirmação e pergunta dentro da página, no lugar de window.confirm / window.prompt.

   Motivo (10/09): o diálogo do navegador trava a extensão que testa e opera o painel,
   e não dá para ler o que está sendo confirmado. Aqui a pergunta é um modal comum:
   dá para ler, tem foco no botão certo, Enter confirma e Esc cancela.

   Uso:
     const perguntar = usePerguntar()
     if (!await perguntar({ titulo: 'Unir os dois cards?', texto: '…', ok: 'Unir' })) return
     const motivo = await perguntar({ titulo: 'Ocultar o aviso?', campo: 'Motivo (opcional)' })
     // com `campo`, devolve o texto (string, pode ser vazia) ou null se cancelar
*/
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'

export interface Pergunta {
  titulo: string
  texto?: ReactNode
  ok?: string
  cancelar?: string
  perigo?: boolean
  campo?: string
  valor?: string
}
type Responder = (p: Pergunta) => Promise<boolean | string | null>

const Ctx = createContext<Responder>(async () => false)

export function PerguntarProvider({ children }: { children: ReactNode }) {
  const [p, setP] = useState<Pergunta | null>(null)
  const [texto, setTexto] = useState('')
  const resolver = useRef<((v: boolean | string | null) => void) | null>(null)
  const inicial = useRef<HTMLButtonElement | null>(null)
  const entrada = useRef<HTMLInputElement | null>(null)

  const perguntar = useCallback<Responder>(q => new Promise(res => {
    resolver.current = res; setTexto(q.valor || ''); setP(q)
  }), [])

  const fechar = useCallback((v: boolean | string | null) => {
    resolver.current?.(v); resolver.current = null; setP(null); setTexto('')
  }, [])

  useEffect(() => {
    if (!p) return
    setTimeout(() => (p.campo ? entrada.current?.focus() : inicial.current?.focus()), 30)
    const h = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { e.preventDefault(); fechar(p.campo ? null : false) }
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); fechar(p.campo ? texto : true) }
    }
    document.addEventListener('keydown', h)
    return () => document.removeEventListener('keydown', h)
  }, [p, texto, fechar])

  const v = useMemo(() => perguntar, [perguntar])
  return <Ctx.Provider value={v}>{children}
    {p && <div className="modal-scrim" role="dialog" aria-modal="true" aria-label={p.titulo} onMouseDown={() => fechar(p.campo ? null : false)}>
      <div className="modal ask" onMouseDown={e => e.stopPropagation()}>
        <h2 className="h1" style={{ fontSize: 20 }}>{p.titulo}</h2>
        {p.texto && <div className="small ink2" style={{ whiteSpace: 'pre-wrap' }}>{p.texto}</div>}
        {p.campo && <div className="field"><label>{p.campo}</label>
          <input ref={entrada} className="input" value={texto} onChange={e => setTexto(e.target.value)} /></div>}
        <div className="row" style={{ justifyContent: 'flex-end' }}>
          <button className="btn" onClick={() => fechar(p.campo ? null : false)}>{p.cancelar || 'Cancelar'}</button>
          <button ref={inicial} className={`btn ${p.perigo ? 'danger' : 'primary'}`} onClick={() => fechar(p.campo ? texto : true)}>{p.ok || 'Confirmar'}</button>
        </div>
      </div>
    </div>}
  </Ctx.Provider>
}

export const usePerguntar = () => useContext(Ctx)
