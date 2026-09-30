import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ApiError } from './client'

export interface Loaded<T> {
  data: T | null; error: ApiError | null; loading: boolean; reload: () => void
}

/** GET com estados loading/error/offline e recarga; refetch opcional por intervalo. */
export function useGet<T>(path: string | null, every?: number): Loaded<T> {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [loading, setLoading] = useState(!!path)
  const [tick, setTick] = useState(0)
  const alive = useRef(true)
  useEffect(() => { alive.current = true; return () => { alive.current = false } }, [])
  useEffect(() => {
    if (!path) { setData(null); setLoading(false); return }
    let cancel = false
    setLoading(true)
    api.get<T>(path).then(d => { if (!cancel && alive.current) { setData(d); setError(null) } })
      .catch((e: ApiError) => { if (!cancel && alive.current) setError(e) })
      .finally(() => { if (!cancel && alive.current) setLoading(false) })
    return () => { cancel = true }
  }, [path, tick])
  useEffect(() => {
    if (!every || !path) return
    const id = setInterval(() => { if (document.visibilityState === 'visible') setTick(t => t + 1) }, every)
    // Aba em segundo plano não faz refetch (economia). Quando volta a ficar visível, busca
    // na hora: foi assim que "gerando…" ficou preso na tela com a geração já concluída.
    const aoVoltar = () => { if (document.visibilityState === 'visible') setTick(t => t + 1) }
    document.addEventListener('visibilitychange', aoVoltar)
    return () => { clearInterval(id); document.removeEventListener('visibilitychange', aoVoltar) }
  }, [every, path])
  const reload = useCallback(() => setTick(t => t + 1), [])
  return { data, error, loading, reload }
}

export function useOnline() {
  const [on, setOn] = useState(navigator.onLine)
  useEffect(() => {
    const up = () => setOn(true), down = () => setOn(false)
    window.addEventListener('online', up); window.addEventListener('offline', down)
    return () => { window.removeEventListener('online', up); window.removeEventListener('offline', down) }
  }, [])
  return on
}

/** Lista paginada no backend (issue #20): busca uma página, "carregar mais" pede a seguinte.
 *  Mudou o filtro (a `base`), recomeça do zero. */
export function usePaginado<T>(base: string, tamanho = 100) {
  const [itens, setItens] = useState<T[]>([])
  const [total, setTotal] = useState(0)
  const [erro, setErro] = useState<ApiError | null>(null)
  const [carregando, setCarregando] = useState(true)
  const [versao, setVersao] = useState(0)
  const sep = base.includes('?') ? '&' : '?'
  useEffect(() => {
    let cancel = false
    setCarregando(true)
    api.pagina<T>(`${base}${sep}limit=${tamanho}&offset=0`)
      .then(r => { if (!cancel) { setItens(r.itens); setTotal(r.total); setErro(null) } })
      .catch((e: ApiError) => { if (!cancel) setErro(e) })
      .finally(() => { if (!cancel) setCarregando(false) })
    return () => { cancel = true }
  }, [base, sep, tamanho, versao])
  const mais = useCallback(async () => {
    setCarregando(true)
    try { const r = await api.pagina<T>(`${base}${sep}limit=${tamanho}&offset=${itens.length}`); setItens(xs => [...xs, ...r.itens]); setTotal(r.total) }
    catch (e) { setErro(e as ApiError) } finally { setCarregando(false) }
  }, [base, sep, tamanho, itens.length])
  const recarregar = useCallback(() => setVersao(v => v + 1), [])
  return { itens, total, erro, carregando, mais, recarregar, temMais: itens.length < total }
}
