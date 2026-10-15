/* De onde a pessoa veio, para o formulário de contato e de pedido levar junto (#260).
 *
 * O site antigo (Contact Form 7) mandava a campanha com a mensagem; o `/contact/` do novo não
 * mandava nada, então Vendas não sabia se o contato veio de anúncio, de busca ou do Instagram.
 *
 * Este script NÃO fala com ninguém de fora e não depende da medição estar ligada: lê a campanha
 * do endereço (e os cookies que o pixel do Meta deixa neste navegador), guarda neste navegador e
 * põe como campo escondido nos formulários do site. Só campanha — nada da pessoa. */
(function () {
  'use strict'
  var CHAVE = 'urace.campanha'
  var MAX = 200
  var DO_ENDERECO = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
    'gclid', 'fbclid', 'campaign_id', 'adset_id']

  function corta(v) {
    return String(v == null ? '' : v).replace(/[<>]/g, ' ').replace(/\s+/g, ' ').trim().slice(0, MAX)
  }
  function cookie(nome) {
    var m = document.cookie.match(new RegExp('(?:^|;\\s*)' + nome + '=([^;]*)'))
    if (!m) return ''
    try { return corta(decodeURIComponent(m[1])) } catch (err) { return corta(m[1]) }
  }

  function doEndereco() {
    var q = new URLSearchParams(window.location.search)
    var out = {}
    DO_ENDERECO.forEach(function (k) {
      var v = corta(q.get(k))
      if (v) out[k] = v
    })
    return out
  }

  function guardado() {
    try { return JSON.parse(window.localStorage.getItem(CHAVE) || '{}') || {} } catch (err) { return {} }
  }

  /** Último clique ganha: chegou com campanha no endereço, é essa que vale daqui para frente. */
  var atual = doEndereco()
  if (Object.keys(atual).length) {
    try { window.localStorage.setItem(CHAVE, JSON.stringify(atual)) } catch (err) { /* sem armazenamento */ }
  } else {
    atual = guardado()
  }

  function ler() {
    var out = {}
    DO_ENDERECO.forEach(function (k) { if (atual[k]) out[k] = corta(atual[k]) })
    var fbp = cookie('_fbp'), fbc = cookie('_fbc')       // o pixel deixa os dois neste navegador
    if (fbp) out.fbp = fbp
    if (fbc) out.fbc = fbc
    return out
  }
  window.uraceCampanha = { ler: ler }

  // Campo escondido em cada formulário do site: vale com JavaScript (fetch) e sem ele (POST normal)
  var campos = ler()
  document.querySelectorAll('form[data-contato], form[data-pedido]').forEach(function (form) {
    Object.keys(campos).forEach(function (k) {
      if (form.elements[k]) return
      var i = document.createElement('input')
      i.type = 'hidden'; i.name = k; i.value = campos[k]
      form.appendChild(i)
    })
  })
})()
