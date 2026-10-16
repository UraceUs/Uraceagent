/* Medição de campanha das páginas públicas (#260).
 *
 * Nada aqui tem id de ninguém: o id do Google Tag Manager e o do pixel do Meta chegam no bloco
 * `application/json#urace-medicao` que o servidor põe no <head> SÓ quando a variável de ambiente
 * existe (`command_center/vitrine/medicao.py`). Sem o bloco, este script não faz nada e nenhuma
 * requisição sai para o Google ou para o Meta.
 *
 * O que vai para o `dataLayer`: `page_view` com o TIPO da página, o `purchase` que o servidor
 * mandou na página do pedido pago, e o `add_to_cart` que o carrinho e a agenda empurram.
 * NUNCA nome, e-mail, telefone, endereço, medida ou piloto.
 *
 * #171 (dono, 15/10: "Sim, banner simples"): o Google e o Meta só carregam depois do "Accept". Sem
 * resposta, um banner pergunta; "Decline" guarda a recusa e nada de fora carrega. A escolha fica no
 * navegador da pessoa (localStorage, com cookie de reserva) e "Cookie settings", no rodapé, pergunta de
 * novo. O `dataLayer` continua recebendo os eventos — sem o GTM, eles não saem da página.
 *
 * #170: o chat do Kommo é o atendimento do site (como no urace.us de hoje), não medição: carrega com a
 * configuração do servidor, independente do banner. */
(function () {
  'use strict'
  var bloco = document.getElementById('urace-medicao')
  if (!bloco) return
  var cfg = {}
  try { cfg = JSON.parse(bloco.textContent || '{}') } catch (err) { return }
  if (!cfg.gtm && !cfg.pixel && !cfg.kommo) return

  // ---------------------------------------------------------------- chat do Kommo (#170)
  // O carregador oficial do widget, sem script inline: o mesmo `crm_plugin` + fila `crmPlugin` do snippet.
  if (cfg.kommo && cfg.kommo.id && cfg.kommo.hash && !window.crm_plugin) {
    window.crm_plugin = { id: String(cfg.kommo.id), hash: String(cfg.kommo.hash), locale: 'en',
      setMeta: function (p) { this.params = (this.params || []).concat([p]) } }
    window.crmPlugin = window.crmPlugin || function () { (window.crmPlugin.q = window.crmPlugin.q || []).push(arguments) }
    var k = document.createElement('script')
    k.async = true; k.id = 'crm_plugin_script'; k.src = 'https://gso.kommo.com/js/button.js'
    document.head.appendChild(k)
  }
  if (!cfg.gtm && !cfg.pixel) return

  // ---------------------------------------------------------------- consentimento (#171)
  var CHAVE = 'urace-consent'
  function lerEscolha() {
    try { var v = window.localStorage.getItem(CHAVE); if (v) return v } catch (err) { /* sem storage */ }
    var m = document.cookie.match(/(?:^|;\s*)urace_consent=(sim|nao)/)
    return m ? m[1] : ''
  }
  function gravarEscolha(v) {
    try { window.localStorage.setItem(CHAVE, v) } catch (err) { /* sem storage: fica o cookie */ }
    document.cookie = 'urace_consent=' + v + '; Max-Age=' + (60 * 60 * 24 * 180) + '; Path=/; SameSite=Lax; Secure'
  }

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
  var carregado = false

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
  doServidor.forEach(function (ev) { empurrar(ev) })

  /** O que o carrinho e a agenda usam: `window.uraceMedicao.push({event:'add_to_cart', …})`. */
  window.uraceMedicao = { push: function (ev) { empurrar(ev); noPixel(ev) } }

  /** O Google e o Meta, só depois do "Accept". O GTM entra por último: os eventos já estão no dataLayer. */
  function carregarDeFora() {
    if (carregado) return
    carregado = true
    if (cfg.pixel) {
      pixelBase(cfg.pixel)
      doServidor.forEach(noPixel)
    }
    if (cfg.gtm) {
      dl.push({ 'gtm.start': new Date().getTime(), event: 'gtm.js' })
      var g = document.createElement('script')
      g.async = true
      g.src = 'https://www.googletagmanager.com/gtm.js?id=' + encodeURIComponent(cfg.gtm)
      document.head.appendChild(g)
    }
  }

  // ---------------------------------------------------------------- o banner
  function banner() {
    if (document.querySelector('.consentimento')) return
    var b = document.createElement('div')
    b.className = 'consentimento'
    b.setAttribute('role', 'region')
    b.setAttribute('aria-label', 'Cookies')
    var p = document.createElement('p')
    p.appendChild(document.createTextNode('We use cookies to measure our ads and improve the site. '))
    var a = document.createElement('a'); a.href = '/legal/privacy.html'; a.textContent = 'Privacy policy'
    p.appendChild(a)
    var acoes = document.createElement('div'); acoes.className = 'consentimento-acoes'
    var nao = document.createElement('button'); nao.type = 'button'; nao.className = 'btn btn-sm btn-linha-escura'; nao.textContent = 'Decline'
    var sim = document.createElement('button'); sim.type = 'button'; sim.className = 'btn btn-sm'; sim.textContent = 'Accept'
    nao.addEventListener('click', function () { gravarEscolha('nao'); fechar() })
    sim.addEventListener('click', function () { gravarEscolha('sim'); fechar(); carregarDeFora() })
    acoes.appendChild(nao); acoes.appendChild(sim)
    b.appendChild(p); b.appendChild(acoes)
    document.body.appendChild(b)
    // #284: o balão do chat (fixo, embaixo à direita) sobe a altura do banner enquanto ele está aberto
    var raiz = document.documentElement
    function medir() { raiz.style.setProperty('--consentimento-altura', (b.offsetHeight + 12) + 'px') }
    medir()
    raiz.classList.add('com-consentimento')
    window.addEventListener('resize', medir)
    function fechar() {
      b.remove()
      raiz.classList.remove('com-consentimento')
      window.removeEventListener('resize', medir)
    }
  }

  var escolha = lerEscolha()
  if (escolha === 'sim') carregarDeFora()
  else if (escolha !== 'nao') {
    if (document.body) banner()
    else document.addEventListener('DOMContentLoaded', banner)
  }
  // "Cookie settings" no rodapé: pergunta de novo
  function ligarRodape() {
    document.querySelectorAll('[data-cookies]').forEach(function (bt) {
      bt.hidden = false
      bt.addEventListener('click', banner)
    })
  }
  if (document.body) ligarRodape()
  else document.addEventListener('DOMContentLoaded', ligarRodape)
})()
