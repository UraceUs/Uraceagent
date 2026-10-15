/* Medição de campanha das páginas públicas (#260).
 *
 * Nada aqui tem id de ninguém: o id do Google Tag Manager e o do pixel do Meta chegam no bloco
 * `application/json#urace-medicao` que o servidor põe no <head> SÓ quando a variável de ambiente
 * existe (`command_center/vitrine/medicao.py`). Sem o bloco, este script não faz nada e nenhuma
 * requisição sai para o Google ou para o Meta.
 *
 * O que vai para o `dataLayer`: `page_view` com o TIPO da página, o `purchase` que o servidor
 * mandou na página do pedido pago, e o `add_to_cart` que o carrinho e a agenda empurram.
 * NUNCA nome, e-mail, telefone, endereço, medida ou piloto. */
(function () {
  'use strict'
  var bloco = document.getElementById('urace-medicao')
  if (!bloco) return
  var cfg = {}
  try { cfg = JSON.parse(bloco.textContent || '{}') } catch (err) { return }
  if (!cfg.gtm && !cfg.pixel) return

  // a volta do Stripe traz `?session_id=…`: esse endereço abre o pedido de uma pessoa, então sai
  // do endereço ANTES de qualquer script de fora (o Analytics manda o endereço inteiro)
  if (cfg.limpar_endereco && window.location.search) {
    try { window.history.replaceState(null, '', window.location.pathname) } catch (err) { /* fica como está */ }
  }

  var dl = (window.dataLayer = window.dataLayer || [])

  /** O tipo da página, do caminho: o relatório separa campanha de loja, de serviço e de blog. */
  function tipo(p) {
    if (p === '/') return 'home'
    if (p.indexOf('/store/p/') === 0) return 'produto'
    if (p.indexOf('/store/') === 0) return 'loja'
    if (p.indexOf('/services/') === 0) return 'servico'
    if (p.indexOf('/blog/') === 0) return 'blog'
    if (p.indexOf('/contact/') === 0) return 'contato'
    if (p.indexOf('/thanks/') >= 0) return 'pedido'
    return 'pagina'
  }

  function empurrar(ev) { if (ev) dl.push(ev) }

  // ---------------------------------------------------------------- pixel do Meta (quando direto)
  // Sem SITE_META_PIXEL_ID o pixel não entra por aqui: ou vem como tag dentro do container do GTM,
  // ou não existe. Posto nos dois lugares, contaria duas vezes — o deploy diz para escolher um.
  function pixelBase(id) {
    if (window.fbq) return
    var n = window.fbq = function () {
      if (n.callMethod) n.callMethod.apply(n, arguments)
      else n.queue.push(arguments)
    }
    if (!window._fbq) window._fbq = n
    n.push = n; n.loaded = true; n.version = '2.0'; n.queue = []
    var fb = document.createElement('script')
    fb.async = true
    fb.src = 'https://connect.facebook.net/en_US/fbevents.js'
    document.head.appendChild(fb)
    n('init', String(id))
    n('track', 'PageView')
  }
  if (cfg.pixel) pixelBase(cfg.pixel)

  /** O mesmo evento no pixel, quando ele está direto aqui (no GTM, a tag do container cuida). */
  function noPixel(ev) {
    if (!cfg.pixel || !window.fbq || !ev || !ev.event) return
    var c = ev.ecommerce || {}
    var dados = { value: c.value, currency: c.currency || 'USD' }
    if (ev.event === 'add_to_cart') window.fbq('track', 'AddToCart', dados)
    else if (ev.event === 'purchase') window.fbq('track', 'Purchase', dados)
  }

  // ---------------------------------------------------------------- o que a página já sabe
  empurrar({ event: 'page_view', page_type: tipo(window.location.pathname) })
  var doServidor = cfg.eventos || []
  doServidor.forEach(function (ev) { empurrar(ev); noPixel(ev) })

  /** O que o carrinho e a agenda usam: `window.uraceMedicao.push({event:'add_to_cart', …})`. */
  window.uraceMedicao = { push: function (ev) { empurrar(ev); noPixel(ev) } }

  // ---------------------------------------------------------------- Google Tag Manager
  // Entra por último: os eventos acima já estão no dataLayer quando o container sobe.
  if (cfg.gtm) {
    dl.push({ 'gtm.start': new Date().getTime(), event: 'gtm.js' })
    var g = document.createElement('script')
    g.async = true
    g.src = 'https://www.googletagmanager.com/gtm.js?id=' + encodeURIComponent(cfg.gtm)
    document.head.appendChild(g)
  }
})()
