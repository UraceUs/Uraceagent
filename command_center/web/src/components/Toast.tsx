import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'

interface T { id: number; text: string; tone?: 'ok' | 'crit' }
const Ctx = createContext<(text: string, tone?: 'ok' | 'crit') => void>(() => {})

export function ToastProvider({ children }: { children: ReactNode }) {
  const [list, setList] = useState<T[]>([])
  const push = useCallback((text: string, tone?: 'ok' | 'crit') => {
    const id = Date.now() + Math.random()
    setList(l => [...l, { id, text, tone }])
    setTimeout(() => setList(l => l.filter(t => t.id !== id)), 5000)
  }, [])
  const v = useMemo(() => push, [push])
  return <Ctx.Provider value={v}>{children}
    <div className="toast-wrap" aria-live="polite">{list.map(t => <div key={t.id} className={`toast ${t.tone || ''}`}>{t.text}</div>)}</div>
  </Ctx.Provider>
}
export const useToast = () => useContext(Ctx)
