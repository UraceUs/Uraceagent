/* Carrinho do site novo (#236).
 *
 * O carrinho mora neste navegador (localStorage) e guarda SÓ as escolhas: produto, opção e quantidade;
 * serviço, dia, turno e piloto. Preço, depósito e vaga quem diz é o servidor (/ops/api/vitrine/carrinho),
 * do catálogo da loja e do painel, toda vez que a página do carrinho abre e antes de pagar.
 *
 * Em toda página: o contador do topo. Na loja: o botão "Add to cart". Na página /cart/: as linhas, a conta
 * do site (a sessão da agenda pede a conta e o piloto) e o botão que abre o Stripe Checkout. */
(function () {
  'use strict'
  var CHAVE = 'urace.carrinho'
  var MAX = 20

  function ler() {
    try {
      var d = JSON.parse(window.localStorage.getItem(CHAVE) || '{}')
      return Array.isArray(d.itens) ? d.itens.slice(0, MAX) : []
    } catch (e) { return [] }
  }
  function gravar(itens) {
    try { window.localStorage.setItem(CHAVE, JSON.stringify({ v: 1, itens: itens.slice(0, MAX) })) } catch (e) { /* sem armazenamento */ }
    contador()
  }
  function contar(itens) {
    return (itens || ler()).reduce(function (n, x) { return n + (x.tipo === 'produto' ? Number(x.quantidade) || 1 : 1) }, 0)
  }
  function contador() {
    var n = contar()
    document.querySelectorAll('[data-carrinho-n]').forEach(function (el) {
      el.textContent = n > 99 ? '99+' : String(n)
      el.hidden = n === 0
      var link = el.closest('a')
      if (link) link.setAttribute('aria-label', n ? 'Cart, ' + n + (n === 1 ? ' item' : ' items') : 'Cart')
    })
  }
  /** Põe no carrinho. Produto igual (mesma opção) soma a quantidade; sessão igual não entra duas vezes. */
  function por(item) {
    var itens = ler()
    if (item.tipo === 'produto') {
      var igual = itens.filter(function (x) { return x.tipo === 'produto' && x.produto === item.produto && (x.variacao || '') === (item.variacao || '') })[0]
      if (igual) igual.quantidade = Math.min(20, (Number(igual.quantidade) || 1) + (Number(item.quantidade) || 1))
      else itens.push({ tipo: 'produto', produto: item.produto, variacao: item.variacao || '', quantidade: Math.max(1, Math.min(20, Number(item.quantidade) || 1)) })
    } else if (item.tipo === 'sessao') {
      var ja = itens.some(function (x) { return x.tipo === 'sessao' && x.servico === item.servico && x.data === item.data && x.turno === item.turno && !x.piloto })
      if (!ja) itens.push({ tipo: 'sessao', servico: Number(item.servico), data: item.data, turno: item.turno, piloto: item.piloto || null })
    }
    if (itens.length > MAX) return false
    gravar(itens)
    return true
  }
  function limpar() { gravar([]) }
  window.uraceCarrinho = { ler: ler, por: por, contar: contar, limpar: limpar }

  function avisoAdicionado(el) {
    if (!el) return
    el.textContent = ''
    el.appendChild(document.createTextNode('Added to your cart. '))
    var a = document.createElement('a')
    a.href = '/cart/'; a.textContent = 'View cart'
    el.appendChild(a)
  }

  // ------------------------------------------------ a loja: "Add to cart" ao lado do "Buy now"
  document.querySelectorAll('form.form-comprar').forEach(function (form) {
    var b = form.querySelector('[data-por-no-carrinho]')
    if (!b) return
    b.hidden = false
    b.addEventListener('click', function () {
      var v = form.querySelector('[name="variacao"]')
      var ok = por({ tipo: 'produto', produto: form.querySelector('[name="produto"]').value, variacao: v ? v.value : '',
        quantidade: form.querySelector('[name="quantidade"]').value })
      var aviso = form.querySelector('.carrinho-ok')
      if (ok) avisoAdicionado(aviso)
      else if (aviso) aviso.textContent = 'Your cart is full (up to ' + MAX + ' items).'
    })
  })

  // ------------------------------------------------ a página do carrinho
  var raiz = document.querySelector('.carrinho[data-api]')
  if (document.querySelector('[data-limpar-carrinho]')) limpar()      // voltou do Stripe com o pedido: o carrinho virou pedido
  contador()
  if (!raiz) return

  var api = raiz.getAttribute('data-api')
  var portal = raiz.getAttribute('data-portal')
  var estado = raiz.querySelector('.carrinho-estado')
  var grade = raiz.querySelector('.carrinho-grade')
  var vazio = raiz.querySelector('.carrinho-vazio')
  var lista = raiz.querySelector('.carrinho-linhas')
  var contaBox = raiz.querySelector('.carrinho-conta')
  var entrega = raiz.querySelector('.carrinho-entrega')
  var total = raiz.querySelector('.carrinho-total')
  var erroEl = raiz.querySelector('.carrinho-erro')
  var pagar = raiz.querySelector('.carrinho-pagar')
  var cot = null, indo = false

  function usd(n) { return '$' + Number(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
  function el(tag, classe, texto) {
    var x = document.createElement(tag)
    if (classe) x.className = classe
    if (texto != null) x.textContent = texto
    return x
  }
  function csrf() {
    var m = document.cookie.match(/(?:^|;\s*)cp_csrf=([^;]+)/)
    return m ? decodeURIComponent(m[1]) : ''
  }
  function erro(msg) {
    erroEl.textContent = msg || ''
    erroEl.hidden = !msg
  }

  function linha(x, conta) {
    var li = el('li', 'carrinho-linha' + (x.erro ? ' com-erro' : ''))
    var topo = el('div', 'carrinho-linha-topo')
    var nome = el('h3', 'carrinho-nome')
    if (x.link) { var a = el('a', null, x.nome); a.href = x.link; nome.appendChild(a) } else nome.textContent = x.nome
    topo.appendChild(nome)
    topo.appendChild(el('strong', 'carrinho-valor', usd(x.valor)))
    li.appendChild(topo)
    if (x.detalhe) li.appendChild(el('p', 'muted small', x.detalhe))
    if (x.tipo === 'produto' && !x.erro && x.quantidade > 1) li.appendChild(el('p', 'muted small', x.quantidade + ' × ' + usd(x.unitario)))
    if (x.deposito > 0) li.appendChild(el('p', 'small', 'Refundable security deposit: ' + usd(x.deposito)))
    var acoes = el('div', 'carrinho-acoes')
    if (x.tipo === 'produto') {
      var q = el('label', 'carrinho-qtd')
      q.appendChild(document.createTextNode('Quantity '))
      var inp = el('input'); inp.type = 'number'; inp.min = '1'; inp.max = '20'; inp.inputMode = 'numeric'; inp.value = String(x.quantidade)
      inp.addEventListener('change', function () {
        var itens = ler(); var it = itens[x.idx]
        if (it) { it.quantidade = Math.max(1, Math.min(20, Number(inp.value) || 1)); gravar(itens); cotar() }
      })
      q.appendChild(inp); acoes.appendChild(q)
    }
    if (x.tipo === 'sessao' && conta) {
      var p = el('label', 'carrinho-piloto')
      p.appendChild(document.createTextNode('Driver '))
      var sel = el('select')
      sel.appendChild(new Option('Choose the driver', ''))
      conta.drivers.forEach(function (d) {
        var o = new Option(d.name + (d.blocked ? ' (' + d.blocked + ')' : ''), String(d.id))
        o.disabled = !!d.blocked
        sel.appendChild(o)
      })
      var livres = conta.drivers.filter(function (d) { return !d.blocked })
      if (x.piloto) sel.value = String(x.piloto)
      else if (livres.length === 1) {                     // um piloto só: já vem escolhido
        sel.value = String(livres[0].id)
        var itens0 = ler(); if (itens0[x.idx]) { itens0[x.idx].piloto = livres[0].id; gravar(itens0); setTimeout(cotar, 0) }
      }
      sel.addEventListener('change', function () {
        var itens = ler(); var it = itens[x.idx]
        if (it) { it.piloto = Number(sel.value) || null; gravar(itens); cotar() }
      })
      p.appendChild(sel); acoes.appendChild(p)
    }
    var tirar = el('button', 'btn btn-sm btn-linha-escura carrinho-tirar', 'Remove')
    tirar.type = 'button'
    tirar.setAttribute('aria-label', 'Remove ' + x.nome)
    tirar.addEventListener('click', function () {
      var itens = ler(); itens.splice(x.idx, 1); gravar(itens); cotar()
    })
    acoes.appendChild(tirar)
    li.appendChild(acoes)
    if (x.erro) {
      var e = el('p', 'carrinho-linha-erro', x.erro)
      if (/Account|profile|measurements/.test(x.erro)) {
        var ir = el('a', null, ' Update it in your account'); ir.href = portal + (/Account/.test(x.erro) ? '/account' : '/drivers')
        e.appendChild(ir)
      }
      li.appendChild(e)
    }
    return li
  }

  function desenharConta(c) {
    contaBox.textContent = ''
    if (!c.tem_sessao) { contaBox.hidden = true; return }
    contaBox.hidden = false
    if (!c.account) {
      contaBox.appendChild(el('p', null, 'Sessions need your URACE account: it keeps your drivers, waivers and bookings.'))
      var acoes = el('p', 'hero-acoes')
      var entrar = el('a', 'btn btn-sm', 'Sign in'); entrar.href = portal + '?volta=cart'
      var criar = el('a', 'btn btn-sm btn-linha-escura', 'Create account'); criar.href = portal + '/signup?volta=cart'
      acoes.appendChild(entrar); acoes.appendChild(criar)
      contaBox.appendChild(acoes)
      return
    }
    var p = el('p', null, 'Signed in as ')
    p.appendChild(el('b', null, c.account.name))
    p.appendChild(el('span', 'muted', ' · ' + c.account.email))
    contaBox.appendChild(p)
    if (!c.account.drivers.length) {
      var add = el('p')
      var a = el('a', 'btn btn-sm', 'Add a driver'); a.href = portal + '/drivers?volta=cart'
      add.appendChild(document.createTextNode('Add the driver (your child, or you) to your account, then come back. '))
      add.appendChild(a)
      contaBox.appendChild(add)
    }
  }

  function desenhar(c) {
    cot = c
    estado.hidden = true
    if (!c.linhas.length) { grade.hidden = true; vazio.hidden = false; return }
    vazio.hidden = true; grade.hidden = false
    lista.textContent = ''
    c.linhas.forEach(function (x) { lista.appendChild(linha(x, c.account)) })
    desenharConta(c)
    entrega.hidden = !c.tem_produto
    total.textContent = ''
    function par(k, v, classe) {
      var dt = el('dt', classe, k), dd = el('dd', classe, v)
      total.appendChild(dt); total.appendChild(dd)
    }
    par('Subtotal', usd(c.subtotal))
    if (c.deposito > 0) par('Security deposit (refundable)', usd(c.deposito))
    par('Total', usd(c.total), 'soma')
    var pronto = c.ok && !c.precisa_conta && c.stripe
    pagar.disabled = !pronto || indo
    pagar.textContent = indo ? 'Opening the secure checkout…' : 'Checkout · ' + usd(c.total)
    erro(c.precisa_conta ? null : c.linhas.some(function (x) { return x.erro }) ? 'Fix the items marked in red to continue.'
      : c.linhas.some(function (x) { return x.falta_piloto }) && c.account && c.account.drivers.length ? 'Choose the driver for each session.' : null)
  }

  function cotar() {
    var itens = ler()
    if (!itens.length) { desenhar({ linhas: [], account: null }); return Promise.resolve() }
    return fetch(api, { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ itens: itens }) })
      .then(function (r) { if (!r.ok) throw new Error(String(r.status)); return r.json() })
      .then(desenhar)
      .catch(function () { estado.hidden = false; estado.textContent = 'We could not load your cart. Please refresh the page.' })
  }

  pagar.addEventListener('click', function () {
    if (!cot || indo) return
    indo = true; erro(null); desenhar(cot)
    var r = entrega.querySelector('input:checked')
    fetch(api + '/checkout', { method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json', 'X-CSRF': csrf() },
      body: JSON.stringify({ itens: ler(), entrega: r ? r.value : 'retirada' }) })
      .then(function (resp) { return resp.json().then(function (d) { return { ok: resp.ok, d: d } }) })
      .then(function (x) {
        if (x.ok && x.d.url) { window.location.assign(x.d.url); return }
        indo = false
        return cotar().then(function () { erro(x.d.erro || 'Something went wrong. Please try again.') })
      })
      .catch(function () { indo = false; desenhar(cot); erro('We could not reach the checkout. Please try again.') })
  })

  cotar()
})()
