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
  // #248: as páginas da compra em inglês ou português (a chave EN/PT grava a escolha; o servidor põe o `lang`)
  var PT = (document.documentElement.lang || '').indexOf('pt') === 0
  function t(en, pt) { return PT ? pt : en }

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
      if (link) link.setAttribute('aria-label', n ? t('Cart, ', 'Carrinho, ') + n + (n === 1 ? t(' item', ' item') : t(' items', ' itens')) : t('Cart', 'Carrinho'))
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
      var ja = itens.filter(function (x) { return x.tipo === 'sessao' && x.servico === item.servico && x.data === item.data && x.turno === item.turno && !x.piloto })[0]
      // #279: o Lead and Follow vai junto da sessão; pedir de novo a mesma sessão com ele só liga o add-on
      if (ja) { if (item.lead_follow) ja.lead_follow = true }
      else itens.push({ tipo: 'sessao', servico: Number(item.servico), data: item.data, turno: item.turno, piloto: item.piloto || null,
        lead_follow: !!item.lead_follow })
    }
    if (itens.length > MAX) return false
    gravar(itens)
    return true
  }
  function limpar() { gravar([]) }
  window.uraceCarrinho = { ler: ler, por: por, contar: contar, limpar: limpar }

  /** #245: "Restore cart" / "Try again" de um pedido que não foi pago. As escolhas dele voltam para o carrinho,
   *  juntas ao que já está aqui e sem duplicar. Preço, depósito e vaga, o servidor confere de novo. */
  function restaurar(itensR) {
    var atuais = ler()
    itensR.forEach(function (x) {
      if (!x || typeof x !== 'object') return
      if (x.tipo === 'produto') {
        var igual = atuais.filter(function (y) { return y.tipo === 'produto' && y.produto === x.produto && (y.variacao || '') === (x.variacao || '') })[0]
        var q = Math.max(1, Math.min(20, Number(x.quantidade) || 1))
        if (igual) igual.quantidade = Math.max(Number(igual.quantidade) || 1, q)
        else atuais.push({ tipo: 'produto', produto: String(x.produto), variacao: x.variacao || '', quantidade: q })
      } else if (x.tipo === 'sessao') {
        var ja = atuais.some(function (y) { return y.tipo === 'sessao' && Number(y.servico) === Number(x.servico) && y.data === x.data && y.turno === x.turno })
        if (!ja) atuais.push({ tipo: 'sessao', servico: Number(x.servico), data: String(x.data), turno: String(x.turno), piloto: Number(x.piloto) || null,
          lead_follow: !!x.lead_follow })
      }
    })
    gravar(atuais.slice(0, MAX))
  }
  var deOutroPedido = document.querySelector('[data-restaurar]')
  if (deOutroPedido) {
    try { restaurar(JSON.parse(deOutroPedido.getAttribute('data-restaurar') || '[]')) } catch (e) { /* nada a restaurar */ }
    deOutroPedido.removeAttribute('data-restaurar')
    try { window.history.replaceState(null, '', '/cart/') } catch (e) { /* fica no endereço do pedido */ }
  }

  function avisoAdicionado(el) {
    if (!el) return
    el.textContent = ''
    el.appendChild(document.createTextNode(t('Added to your cart. ', 'Foi para o carrinho. ')))
    var a = document.createElement('a')
    a.href = '/cart/'; a.textContent = t('View cart', 'Ver o carrinho')
    el.appendChild(a)
  }

  /** #260: o `add_to_cart` da campanha. Só catálogo, valor e moeda — nada da pessoa. Sem medição
   *  configurada, `window.uraceMedicao` não existe e isto não faz nada. */
  function medir(ev) { if (window.uraceMedicao) window.uraceMedicao.push(ev) }

  // ------------------------------------------------ a loja: "Add to cart" ao lado do "Buy now"
  document.querySelectorAll('form.form-comprar').forEach(function (form) {
    var b = form.querySelector('[data-por-no-carrinho]')
    if (!b) return
    b.hidden = false
    b.addEventListener('click', function () {
      var v = form.querySelector('[name="variacao"]')
      var slug = form.querySelector('[name="produto"]').value
      var qtd = Math.max(1, Math.min(20, Number(form.querySelector('[name="quantidade"]').value) || 1))
      var ok = por({ tipo: 'produto', produto: slug, variacao: v ? v.value : '',
        quantidade: form.querySelector('[name="quantidade"]').value })
      var aviso = form.querySelector('.carrinho-ok')
      if (ok) avisoAdicionado(aviso)
      else if (aviso) aviso.textContent = t('Your cart is full (up to ' + MAX + ' items).', 'O carrinho está cheio (até ' + MAX + ' itens).')
      if (!ok) return
      var op = v && v.selectedOptions && v.selectedOptions[0]
      var preco = Number((op && op.getAttribute('data-preco')) || form.getAttribute('data-preco')) || 0
      medir({ event: 'add_to_cart', ecommerce: { currency: 'USD', value: Math.round(preco * qtd * 100) / 100,
        items: [{ item_id: slug, item_name: form.getAttribute('data-nome') || slug, item_category: 'produto',
          item_variant: v ? v.value : undefined, price: preco, quantity: qtd }] } })
    })
  })

  // ------------------------------------------------ a página do carrinho
  var raiz = document.querySelector('.carrinho[data-api]')
  if (document.querySelector('[data-limpar-carrinho]')) limpar()      // voltou do Stripe com o pedido: o carrinho virou pedido
  // #282: o ⓘ abre no toque (celular) e fecha no segundo toque, num toque fora ou no Esc. O mouse e o
  // teclado abrem pelo CSS (:hover e :focus-within). Roda em toda página pública: a reserva, o carrinho e o pedido.
  function fecharDicas(menos) {
    var abertas = document.querySelectorAll('.dica.aberta')
    for (var i = 0; i < abertas.length; i++) {
      if (abertas[i] === menos) continue
      abertas[i].classList.remove('aberta')
      abertas[i].querySelector('.dica-botao').setAttribute('aria-expanded', 'false')
    }
  }
  // a caixa do texto fica sempre inteira na tela (16 px de margem), acima do ⓘ ou abaixo, se não couber
  function posicionar(caixa) {
    var txt = caixa.querySelector('.dica-texto'), r = caixa.getBoundingClientRect()
    var tela = document.documentElement.clientWidth || window.innerWidth   // a largura do layout, não a do zoom
    var w = Math.min(270, tela - 32)
    txt.style.width = w + 'px'
    var esq = Math.max(16, Math.min(r.left + r.width / 2 - w / 2, tela - 16 - w))
    txt.style.left = Math.round(esq - r.left) + 'px'
    caixa.classList.toggle('embaixo', r.top < txt.offsetHeight + 24)
  }
  function aoChegar(ev) {
    var caixa = ev.target.closest && ev.target.closest('.dica')
    if (caixa) posicionar(caixa)
  }
  document.addEventListener('mouseover', aoChegar)
  document.addEventListener('focusin', aoChegar)
  document.addEventListener('click', function (ev) {
    var b = ev.target.closest && ev.target.closest('.dica-botao')
    if (!b) { if (!(ev.target.closest && ev.target.closest('.dica-texto'))) fecharDicas(null); return }
    var caixa = b.parentNode
    posicionar(caixa)
    fecharDicas(caixa)
    var abrir = !caixa.classList.contains('aberta')
    caixa.classList.toggle('aberta', abrir)
    b.setAttribute('aria-expanded', abrir ? 'true' : 'false')
  })
  document.addEventListener('keydown', function (ev) { if (ev.key === 'Escape') fecharDicas(null) })

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
  // #282 (dono, 15/10): o ⓘ do security deposit. O mesmo texto de `vitrine/dica.py` (o teste confere).
  var DEPOSITO_INFO = 'Refundable within 5 days after your session, as long as there is no damage to the kart. Damage above the deposit amount may be charged additionally.'
  var DEPOSITO_INFO_PT = 'Reembolsável em até 5 dias após a sessão, desde que não haja nenhum dano ao kart. Danos acima do valor do depósito podem ser cobrados adicionalmente.'
  function dicaDeposito() {
    var caixa = el('span', 'dica')
    var b = el('button', 'dica-botao'); b.type = 'button'
    b.setAttribute('aria-expanded', 'false')
    b.setAttribute('aria-label', t('About the security deposit', 'Sobre o depósito de segurança'))
    var NS = 'http://www.w3.org/2000/svg'
    var svg = document.createElementNS(NS, 'svg')
    svg.setAttribute('viewBox', '0 0 24 24'); svg.setAttribute('width', '18'); svg.setAttribute('height', '18')
    svg.setAttribute('aria-hidden', 'true'); svg.setAttribute('focusable', 'false')
    var c1 = document.createElementNS(NS, 'circle')
    c1.setAttribute('cx', '12'); c1.setAttribute('cy', '12'); c1.setAttribute('r', '9.5')
    c1.setAttribute('fill', 'none'); c1.setAttribute('stroke', 'currentColor'); c1.setAttribute('stroke-width', '2')
    var p1 = document.createElementNS(NS, 'path')
    p1.setAttribute('d', 'M12 11v6M12 7.6v.2'); p1.setAttribute('stroke', 'currentColor')
    p1.setAttribute('stroke-width', '2.4'); p1.setAttribute('stroke-linecap', 'round')
    svg.appendChild(c1); svg.appendChild(p1); b.appendChild(svg)
    var txt = el('span', 'dica-texto', t(DEPOSITO_INFO, DEPOSITO_INFO_PT)); txt.setAttribute('role', 'tooltip')
    caixa.appendChild(b); caixa.appendChild(txt)
    return caixa
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
    if (x.deposito > 0) {
      var pd = el('p', 'small', t('Refundable security deposit: ', 'Depósito de segurança reembolsável: ') + usd(x.deposito) + ' ')
      pd.appendChild(dicaDeposito())
      li.appendChild(pd)
    }
    if (x.aviso) li.appendChild(el('p', 'carrinho-aviso small', x.aviso))           // #279: o kart próprio chega 2 dias antes
    var acoes = el('div', 'carrinho-acoes')
    if (x.tipo === 'produto') {
      var q = el('label', 'carrinho-qtd')
      q.appendChild(document.createTextNode(t('Quantity ', 'Quantidade ')))
      var inp = el('input'); inp.type = 'number'; inp.min = '1'; inp.max = '20'; inp.inputMode = 'numeric'; inp.value = String(x.quantidade)
      inp.addEventListener('change', function () {
        var itens = ler(); var it = itens[x.idx]
        if (it) { it.quantidade = Math.max(1, Math.min(20, Number(inp.value) || 1)); gravar(itens); cotar() }
      })
      q.appendChild(inp); acoes.appendChild(q)
    }
    if (x.tipo === 'sessao' && conta) {
      var p = el('label', 'carrinho-piloto')
      p.appendChild(document.createTextNode(t('Driver ', 'Piloto ')))
      var sel = el('select')
      sel.appendChild(new Option(t('Choose the driver', 'Escolha o piloto'), ''))
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
    var tirar = el('button', 'btn btn-sm btn-linha-escura carrinho-tirar', t('Remove', 'Tirar'))
    tirar.type = 'button'
    tirar.setAttribute('aria-label', t('Remove ', 'Tirar ') + x.nome)
    tirar.addEventListener('click', function () {
      var itens = ler()
      // #279: tirar o Lead and Follow só desliga o add-on; a sessão fica no carrinho
      if (x.tipo === 'addon') { if (itens[x.idx]) itens[x.idx].lead_follow = false }
      else itens.splice(x.idx, 1)
      gravar(itens); cotar()
    })
    acoes.appendChild(tirar)
    li.appendChild(acoes)
    if (x.erro) {
      var e = el('p', 'carrinho-linha-erro', x.erro)
      if (/Account|profile|measurements|perfil|medidas/.test(x.erro)) {
        var ir = el('a', null, t(' Update it in your account', ' Atualize na sua conta')); ir.href = portal + (/Account/.test(x.erro) ? '/account' : '/drivers')
        e.appendChild(ir)
      }
      li.appendChild(e)
    }
    return li
  }

  function desenharConta(c) {
    contaBox.textContent = ''
    if (!c.linhas.length) { contaBox.hidden = true; return }       // #248: toda compra pede a conta do site
    contaBox.hidden = false
    if (!c.account) {
      contaBox.appendChild(el('p', null, t('Your URACE account is needed to buy: it keeps your orders, drivers, waivers and bookings.',
        'Para comprar, é preciso a sua conta URACE: ela guarda os seus pedidos, pilotos, waivers e reservas.')))
      var acoes = el('p', 'hero-acoes')
      var entrar = el('a', 'btn btn-sm', t('Sign in', 'Entrar')); entrar.href = portal + '?volta=cart'
      var criar = el('a', 'btn btn-sm btn-linha-escura', t('Create account', 'Criar conta')); criar.href = portal + '/signup?volta=cart'
      acoes.appendChild(entrar); acoes.appendChild(criar)
      contaBox.appendChild(acoes)
      return
    }
    var p = el('p', null, t('Signed in as ', 'Conectado como '))
    p.appendChild(el('b', null, c.account.name))
    p.appendChild(el('span', 'muted', ' · ' + c.account.email))
    contaBox.appendChild(p)
    if (c.tem_sessao && !c.account.drivers.length) {
      var add = el('p')
      var a = el('a', 'btn btn-sm', t('Add a driver', 'Pôr um piloto')); a.href = portal + '/drivers?volta=cart'
      add.appendChild(document.createTextNode(t('Add the driver (your child, or you) to your account, then come back. ',
        'Ponha o piloto (o seu filho, ou você) na sua conta e volte aqui. ')))
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
    function par(k, v, classe, extra) {
      var dt = el('dt', classe, k), dd = el('dd', classe, v)
      if (extra) { dt.appendChild(document.createTextNode(' ')); dt.appendChild(extra) }
      total.appendChild(dt); total.appendChild(dd)
    }
    par('Subtotal', usd(c.subtotal))
    if (c.deposito > 0) par(t('Security deposit (refundable)', 'Depósito de segurança (reembolsável)'), usd(c.deposito), null, dicaDeposito())
    par('Total', usd(c.total), 'soma')
    var pronto = c.ok && !c.precisa_conta && c.stripe
    pagar.disabled = !pronto || indo
    pagar.textContent = indo ? t('Opening the secure checkout…', 'Abrindo o pagamento seguro…') : t('Checkout · ', 'Pagar · ') + usd(c.total)
    erro(c.precisa_conta ? null : c.linhas.some(function (x) { return x.erro }) ? t('Fix the items marked in red to continue.', 'Corrija os itens em vermelho para continuar.')
      : c.linhas.some(function (x) { return x.falta_piloto }) && c.account && c.account.drivers.length ? t('Choose the driver for each session.', 'Escolha o piloto de cada sessão.') : null)
  }

  function cotar() {
    var itens = ler()
    if (!itens.length) { desenhar({ linhas: [], account: null }); return Promise.resolve() }
    return fetch(api, { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ itens: itens }) })
      .then(function (r) { if (!r.ok) throw new Error(String(r.status)); return r.json() })
      .then(desenhar)
      .catch(function () { estado.hidden = false; estado.textContent = t('We could not load your cart. Please refresh the page.', 'Não conseguimos carregar o seu carrinho. Recarregue a página.') })
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
        return cotar().then(function () { erro(x.d.erro || t('Something went wrong. Please try again.', 'Algo deu errado. Tente de novo.')) })
      })
      .catch(function () { indo = false; desenhar(cot); erro(t('We could not reach the checkout. Please try again.', 'Não conseguimos abrir o pagamento. Tente de novo.')) })
  })

  cotar()
})()
