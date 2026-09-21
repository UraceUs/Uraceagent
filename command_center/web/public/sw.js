/* Service worker do Command Center.
 *
 * Faz uma coisa só, e de propósito: receber a notificação e abrir o painel no lugar certo.
 * NÃO guarda página em cache. Um sistema que muda várias vezes por dia com cache agressivo
 * dá o pior dos defeitos: a pessoa jura que o conserto não veio, e veio — ela é que está
 * vendo a versão velha. Enquanto o painel mudar toda hora, cache fica fora.
 *
 * O aviso não traz o texto da mensagem: só quem escreveu, onde, e o link (ver push.py). */
self.addEventListener('install', e => self.skipWaiting())
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()))

self.addEventListener('push', e => {
  let d = { titulo: 'URACE', corpo: 'Novidade no painel', url: '/ops/' }
  try { d = { ...d, ...e.data.json() } } catch { /* payload estranho: mostra o padrão */ }
  e.waitUntil(self.registration.showNotification(d.titulo, {
    body: d.corpo,
    icon: '/ops/icone-192.png',
    badge: '/ops/icone-192.png',
    data: { url: d.url },
    // mesma conversa não empilha cinco avisos na tela de bloqueio
    tag: d.url,
    renotify: true,
  }))
})

self.addEventListener('notificationclick', e => {
  e.notification.close()
  const destino = (e.notification.data && e.notification.data.url) || '/ops/'
  e.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(janelas => {
    // se o painel já está aberto, leva a janela existente para lá em vez de abrir outra
    for (const j of janelas) {
      if (j.url.includes('/ops/') && 'focus' in j) { j.navigate(destino); return j.focus() }
    }
    return self.clients.openWindow(destino)
  }))
})
