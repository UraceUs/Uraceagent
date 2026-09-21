/* Ligar a notificação no celular.
 *
 * Dono, 21/09: o chat interno só substitui o WhatsApp se tocar no celular. Este é o botão
 * que faz isso — e a tela tem de ser honesta sobre onde a pessoa está:
 *
 *  - no iPhone, notificação SÓ funciona com o painel adicionado à tela inicial. Pedir
 *    permissão antes disso falha em silêncio e a pessoa conclui que "não funciona";
 *  - permissão negada não tem volta pelo site: só nos ajustes do navegador. Dizer isso é
 *    melhor do que um botão que não faz nada;
 *  - depois de ligar, um teste de verdade. "Ativei e não sei se funciona" é o jeito mais
 *    rápido de alguém desistir. */
import { useEffect, useState } from 'react'
import { api, ApiError } from '../api/client'
import { useToast } from './Toast'
import { Banner, Chip, Spinner } from './ui'

const naTelaInicial = () => window.matchMedia('(display-mode: standalone)').matches ||
  (window.navigator as unknown as { standalone?: boolean }).standalone === true
const ehIOS = () => /iphone|ipad|ipod/i.test(navigator.userAgent)

function base64ParaBytes(b64: string) {
  const completo = (b64 + '='.repeat((4 - b64.length % 4) % 4)).replace(/-/g, '+').replace(/_/g, '/')
  const bruto = atob(completo)
  return Uint8Array.from([...bruto].map(c => c.charCodeAt(0)))
}

export function Avisos() {
  const toast = useToast()
  const [permissao, setPermissao] = useState<NotificationPermission | 'indisponivel'>('default')
  const [assinado, setAssinado] = useState(false)
  const [busy, setBusy] = useState<string | null>(null)
  const [servidorOk, setServidorOk] = useState<boolean | null>(null)

  useEffect(() => {
    if (!('Notification' in window) || !('serviceWorker' in navigator) || !('PushManager' in window)) {
      setPermissao('indisponivel'); return
    }
    setPermissao(Notification.permission)
    navigator.serviceWorker.getRegistration().then(reg => reg?.pushManager.getSubscription()
      .then(s => setAssinado(!!s)))
    api.get<{ ativo: boolean }>('/push/chave').then(r => setServidorOk(r.ativo)).catch(() => setServidorOk(false))
  }, [])

  async function ligar() {
    setBusy('ligar')
    try {
      const { ativo, chave } = await api.get<{ ativo: boolean; chave?: string }>('/push/chave')
      if (!ativo || !chave) throw new Error('O servidor ainda não está pronto para notificar.')
      const permissao = await Notification.requestPermission()
      setPermissao(permissao)
      if (permissao !== 'granted') { toast('Sem permissão, o aviso não chega.', 'crit'); return }
      const reg = await navigator.serviceWorker.register('/ops/sw.js', { scope: '/ops/' })
      await navigator.serviceWorker.ready
      const assinatura = await reg.pushManager.subscribe({
        userVisibleOnly: true, applicationServerKey: base64ParaBytes(chave),
      })
      const j = assinatura.toJSON() as { endpoint: string; keys: { p256dh: string; auth: string } }
      await api.post('/push/assinar', { endpoint: j.endpoint, p256dh: j.keys.p256dh, auth: j.keys.auth })
      setAssinado(true)
      toast('Notificação ligada neste aparelho.', 'ok')
    } catch (e) {
      toast(e instanceof Error ? e.message : (e as ApiError).message, 'crit')
    } finally { setBusy(null) }
  }

  async function desligar() {
    setBusy('desligar')
    try {
      const reg = await navigator.serviceWorker.getRegistration()
      const s = await reg?.pushManager.getSubscription()
      if (s) { await api.post('/push/cancelar', { endpoint: s.endpoint }); await s.unsubscribe() }
      setAssinado(false); toast('Notificação desligada neste aparelho.', 'ok')
    } catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(null) }
  }

  async function testar() {
    setBusy('teste')
    try { await api.post('/push/teste'); toast('Mandei. Deve chegar em segundos.', 'ok') }
    catch (e) { toast((e as ApiError).message, 'crit') } finally { setBusy(null) }
  }

  if (permissao === 'indisponivel') return <Banner tone="warn">Este navegador não faz notificação. No celular, use o Chrome (Android) ou o Safari (iPhone).</Banner>
  if (servidorOk === false) return <Banner tone="warn">O servidor ainda não está pronto para notificar — falta a biblioteca de push. Me avise.</Banner>

  // iPhone: sem estar na tela inicial, pedir permissão falha calado
  if (ehIOS() && !naTelaInicial()) return <Banner tone="warn">
    <b>No iPhone, primeiro instale o painel na tela inicial.</b> Toque em Compartilhar
    (o quadrado com a seta) → <b>Adicionar à Tela de Início</b>. Depois abra o painel por esse ícone
    e volte aqui para ligar a notificação. É exigência da Apple, não do painel.
  </Banner>

  if (permissao === 'denied') return <Banner tone="crit">
    A notificação foi <b>bloqueada</b> neste aparelho. O site não consegue perguntar de novo: libere nos
    ajustes do navegador (site urace-bridge.duckdns.org → Notificações → Permitir) e recarregue.
  </Banner>

  return <div className="row wrap" style={{ gap: 8, alignItems: 'center' }}>
    {assinado ? <>
      <Chip tone="ok">avisos ligados neste aparelho</Chip>
      <button className="btn sm" disabled={!!busy} onClick={testar}>{busy === 'teste' ? <Spinner /> : 'Mandar um teste'}</button>
      <button className="btn sm" disabled={!!busy} onClick={desligar}>{busy === 'desligar' ? <Spinner /> : 'Desligar aqui'}</button>
    </> : <>
      <button className="btn primary sm" disabled={!!busy} onClick={ligar}>{busy === 'ligar' ? <Spinner /> : 'Ligar notificação neste aparelho'}</button>
      <span className="small muted">Avisa quando alguém escrever para você, mesmo com o painel fechado.</span>
    </>}
  </div>
}
