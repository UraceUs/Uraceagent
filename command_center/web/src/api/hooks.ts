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
    return () => clearInterval(id)
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
