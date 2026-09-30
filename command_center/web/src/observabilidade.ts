/* Observabilidade do navegador (issue #17): erro de JavaScript e Web Vitals vão para o
 * servidor (POST /ops/api/system/cliente), que mostra em Integrações › Saúde do painel.
 * Sem biblioteca: PerformanceObserver direto. Nada de dado de cliente — só a rota
 * (o servidor troca id por :id), a mensagem do erro e os números. */
const URL_ = '/ops/api/system/cliente'
type Item = { tipo: 'vital' | 'erro'; nome?: string; valor?: number; rota: string; mensagem?: string; origem?: string; pilha?: string }
const fila: Item[] = []
let erros = 0

function enviar(itens: Item[]) {
  if (!itens.length) return
  const corpo = JSON.stringify({ itens: itens.slice(0, 20) })
  if (corpo.length > 4000) return
  try {
    if (navigator.sendBeacon && navigator.sendBeacon(URL_, new Blob([corpo], { type: 'application/json' }))) return
    void fetch(URL_, { method: 'POST', body: corpo, keepalive: true, headers: { 'Content-Type': 'application/json' } }).catch(() => {})
  } catch { /* observabilidade nunca derruba a tela */ }
}

function rota() { return location.pathname }

function erro(mensagem: string, origem?: string, pilha?: string) {
  if (++erros > 10) return                       // uma tela em laço de erro não inunda o servidor
  enviar([{ tipo: 'erro', rota: rota(), mensagem: mensagem.slice(0, 300), origem: origem?.slice(0, 200), pilha: pilha?.slice(0, 800) }])
}

function vital(nome: string, valor: number) { fila.push({ tipo: 'vital', nome, valor, rota: rota() }) }

function observar(tipo: string, fn: (l: PerformanceEntryList) => void, extra: Record<string, unknown> = {}) {
  try { new PerformanceObserver(l => fn(l.getEntries())).observe({ type: tipo, buffered: true, ...extra } as PerformanceObserverInit) }
  catch { /* navegador sem esse tipo */ }
}

export function iniciarObservabilidade() {
  window.addEventListener('error', e => erro(String(e.message || 'erro'), e.filename ? `${e.filename}:${e.lineno}` : undefined, (e.error as Error | undefined)?.stack))
  window.addEventListener('unhandledrejection', e => { const r = e.reason as Error | string; erro(typeof r === 'string' ? r : r?.message || 'promise rejeitada', undefined, typeof r === 'string' ? undefined : r?.stack) })

  let lcp = 0, cls = 0, inp = 0
  observar('largest-contentful-paint', es => { const u = es[es.length - 1]; if (u) lcp = u.startTime })
  observar('layout-shift', es => { for (const e of es as (PerformanceEntry & { value: number; hadRecentInput: boolean })[]) if (!e.hadRecentInput) cls += e.value })
  observar('event', es => { for (const e of es) inp = Math.max(inp, e.duration) }, { durationThreshold: 40 })
  observar('paint', es => { const f = es.find(e => e.name === 'first-contentful-paint'); if (f) vital('FCP', f.startTime) })
  const nav = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming | undefined
  if (nav) vital('TTFB', nav.responseStart)

  let mandou = false
  const fechar = () => {
    if (!mandou) { mandou = true; if (lcp) vital('LCP', lcp); vital('CLS', cls); if (inp) vital('INP', inp) }
    enviar(fila.splice(0))
  }
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden') fechar() })
  window.addEventListener('pagehide', fechar)
}
