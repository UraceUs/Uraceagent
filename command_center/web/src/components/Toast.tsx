import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'

/* `warn` entrou em 23/09 com o cadastro de peça: "a peça foi cadastrada, mas a foto
   não" não é sucesso nem falha, e usar 'crit' ali assustaria por causa de uma imagem. */
type Tom = 'ok' | 'crit' | 'warn'
interface T { id: number; text: string; tone?: Tom }
const Ctx = createContext<(text: string, tone?: Tom) => void>(() => {})

export function ToastProvider({ children }: { children: ReactNode }) {
  const [list, setList] = useState<T[]>([])
  const push = useCallback((text: string, tone?: Tom) => {
    const id = Date.now() + Math.random()
    setList(l => [...l, { id, text, tone }])
    setTimeout(() => setList(l => l.filter(t => t.id !== id)), 5000)
  }, [])
  const v = useMemo(() => push, [push])
  return <Ctx.Provider value={v}>{children}
    <div className="toast-wrap" aria-live="polite">{list.map(t => <div key={t.id} className={`toast ${t.tone || ''}`}><span className="ic" aria-hidden="true">{t.tone === 'ok' ? '✓' : t.tone === 'crit' ? '✕' : t.tone === 'warn' ? '▲' : '●'}</span><div className="grow"><div className="tt">{t.tone === 'ok' ? 'Feito' : t.tone === 'crit' ? 'Não deu' : t.tone === 'warn' ? 'Quase' : 'Aviso'}</div>{t.text}</div></div>)}</div>
  </Ctx.Provider>
}
export const useToast = () => useContext(Ctx)
