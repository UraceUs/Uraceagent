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
      var tx = abertas[i].querySelector('.dica-texto'); tx.style.left = ''; tx.style.right = ''
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
    txt.style.left = Math.round(esq - r.left) + 'px'; txt.style.right = 'auto'
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
  var cadastro = raiz.querySelector('.carrinho-cadastro')         // #305: os dados do comprador, no próprio carrinho
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
  var DEPOSITO_INFO = 'Refundable within 5 business days after your session, as long as there is no damage to the kart. Damage above the deposit amount may be charged additionally.'
  var DEPOSITO_INFO_PT = 'Reembolsável em até 5 dias úteis após a sessão, desde que não haja nenhum dano ao kart. Danos acima do valor do depósito podem ser cobrados adicionalmente.'
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
  function erro(msg, entrar) {
    erroEl.textContent = msg || ''
    if (msg && entrar) {                                            // #305: o e-mail já tem conta: entrar e voltar
      var a = el('a', null, ' ' + t('Sign in', 'Entrar')); a.href = portal + '?volta=cart'
      erroEl.appendChild(a)
    }
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
    if (x.aviso_piloto) li.appendChild(el('p', 'carrinho-aviso-piloto small', x.aviso_piloto))   // #305: completar depois
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
        // #305: o piloto incompleto também vale (completa depois do pagamento, com lembrete por e-mail)
        var o = new Option(d.name + (d.blocked ? ' (' + d.blocked + ')' : d.pending ? ' (' + t('complete after payment', 'completar depois do pagamento') + ')' : ''), String(d.id))
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
    if (cadastro) cadastro.hidden = true
    if (!c.linhas.length) { contaBox.hidden = true; return }       // #248: toda compra pede a conta do site
    if (!c.account && cadastro) {
      // #305 (dono, 16/10): em vez de "Sign in / Create account", os dados dela aqui; no checkout, viram a conta
      contaBox.hidden = true
      cadastro.hidden = false
      cadastro.querySelector('.cad-piloto').hidden = !c.tem_sessao
      return
    }
    contaBox.hidden = false
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
    // #298: o frete fixo de cada produto (do painel); o que não tem valor a equipe combina à parte
    var freteTxt = entrega.querySelector('.carrinho-frete-txt')
    if (freteTxt) {
      freteTxt.textContent = c.frete_a_combinar
        ? (c.frete_envio > 0 ? t('shipping ' + usd(c.frete_envio) + ', and we confirm the rest separately', 'frete de ' + usd(c.frete_envio) + ', e o resto confirmamos à parte')
          : t('we confirm and bill shipping separately', 'confirmamos e cobramos o frete à parte'))
        : (c.frete_envio > 0 ? t('shipping ' + usd(c.frete_envio), 'frete de ' + usd(c.frete_envio)) : t('free shipping', 'frete grátis'))
    }
    total.textContent = ''
    function par(k, v, classe, extra) {
      var dt = el('dt', classe, k), dd = el('dd', classe, v)
      if (extra) { dt.appendChild(document.createTextNode(' ')); dt.appendChild(extra) }
      total.appendChild(dt); total.appendChild(dd)
    }
    par('Subtotal', usd(c.subtotal))
    if (c.deposito > 0) par(t('Security deposit (refundable)', 'Depósito de segurança (reembolsável)'), usd(c.deposito), null, c.tem_sessao ? dicaDeposito() : null)
    if (c.tem_produto && c.entrega === 'envio') {
      par(t('Shipping', 'Frete'), c.frete > 0 ? usd(c.frete) : (c.frete_a_combinar ? t('to confirm', 'a confirmar') : t('Free', 'Grátis')))
    }
    par('Total', usd(c.total), 'soma')
    var pronto = c.ok && c.stripe                                   // #305: sem conta, os dados vão no checkout
    pagar.disabled = !pronto || indo
    pagar.textContent = indo ? t('Opening the secure checkout…', 'Abrindo o pagamento seguro…') : t('Checkout · ', 'Pagar · ') + usd(c.total)
    erro(c.precisa_conta ? null : c.linhas.some(function (x) { return x.erro }) ? t('Fix the items marked in red to continue.', 'Corrija os itens em vermelho para continuar.')
      : c.linhas.some(function (x) { return x.falta_piloto }) && c.account && c.account.drivers.length ? t('Choose the driver for each session.', 'Escolha o piloto de cada sessão.') : null)
  }

  function cotar() {
    var itens = ler()
    if (!itens.length) { desenhar({ linhas: [], account: null }); return Promise.resolve() }
    var r = entrega.querySelector('input:checked')
    return fetch(api, { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ itens: itens, entrega: r ? r.value : 'retirada' }) })
      .then(function (r) { if (!r.ok) throw new Error(String(r.status)); return r.json() })
      .then(desenhar)
      .catch(function () { estado.hidden = false; estado.textContent = t('We could not load your cart. Please refresh the page.', 'Não conseguimos carregar o seu carrinho. Recarregue a página.') })
  }

  entrega.addEventListener('change', function () { if (!indo) cotar() })    // #298: o frete entra (ou sai) do total

  // ------------------------------------------------ #305: os dados do comprador (sem conta ainda)
  if (cadastro) {
    var pais = cadastro.querySelector('[name="country"]'), ddi = cadastro.querySelector('[name="phone_country"]')
    pais.addEventListener('change', function () {
      var op = pais.selectedOptions[0]
      if (op && op.getAttribute('data-ddi')) ddi.value = op.getAttribute('data-ddi')
    })
    cadastro.addEventListener('change', function (ev) {
      if (ev.target.name === 'piloto_eu') cadastro.querySelector('.cad-piloto-nome').hidden = ev.target.value !== '0'
      if (ev.target.getAttribute('aria-invalid')) ev.target.removeAttribute('aria-invalid')
    })
    cadastro.addEventListener('submit', function (ev) { ev.preventDefault(); pagar.click() })
  }
  function campo(n) { var x = cadastro.querySelector('[name="' + n + '"]'); return x ? x.value.trim() : '' }
  /** Os dados que viram a conta, conferidos aqui antes (o servidor confere tudo de novo). Null: falta algo. */
  function dadosDaConta() {
    var faltam = [], obrig = ['name', 'birth_date', 'email', 'phone', 'address_line1', 'city', 'password', 'password2']
    cadastro.querySelectorAll('[aria-invalid]').forEach(function (x) { x.removeAttribute('aria-invalid') })
    function marca(n) { var x = cadastro.querySelector('[name="' + n + '"]'); if (x) { x.setAttribute('aria-invalid', 'true'); faltam.push(x) } }
    obrig.forEach(function (n) { if (!campo(n)) marca(n) })
    if (campo('email') && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(campo('email'))) marca('email')
    var eu = (cadastro.querySelector('[name="piloto_eu"]:checked') || {}).value !== '0'
    if (cot.tem_sessao && !eu && !campo('piloto_nome')) marca('piloto_nome')
    var senha = cadastro.querySelector('[name="password"]').value, senha2 = cadastro.querySelector('[name="password2"]').value
    if (faltam.length) { faltam[0].focus(); erro(t('Fill in the fields marked in red.', 'Preencha os campos em vermelho.')); return null }
    if (senha.length < 8) { marca('password'); faltam[0].focus(); erro(t('Use a password with at least 8 characters.', 'Use uma senha com pelo menos 8 caracteres.')); return null }
    if (senha !== senha2) { marca('password2'); faltam[0].focus(); erro(t("The passwords don't match.", 'As senhas não são iguais.')); return null }
    if (!cadastro.querySelector('[name="accept_terms"]').checked) {
      cadastro.querySelector('[name="accept_terms"]').focus()
      erro(t('Accept the terms and the privacy policy to continue.', 'Para continuar, aceite os termos e a política de privacidade.')); return null
    }
    var d = { accept_terms: true, password: senha, password2: senha2, piloto: { eu: eu, nome: campo('piloto_nome') } }
    ;['name', 'birth_date', 'email', 'phone_country', 'phone', 'address_line1', 'address_line2', 'city', 'state', 'zip', 'country']
      .forEach(function (n) { d[n] = campo(n) })
    return d
  }

  pagar.addEventListener('click', function () {
    if (!cot || indo) return
    var conta = null
    if (cot.precisa_conta && cadastro) {
      conta = dadosDaConta()
      if (!conta) return
    }
    indo = true; erro(null); desenhar(cot)
    var r = entrega.querySelector('input:checked')
    var corpo = { itens: ler(), entrega: r ? r.value : 'retirada' }
    if (conta) corpo.conta = conta
    fetch(api + '/checkout', { method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json', 'X-CSRF': csrf() },
      body: JSON.stringify(corpo) })
      .then(function (resp) { return resp.json().then(function (d) { return { ok: resp.ok, d: d } }) })
      .then(function (x) {
        if (x.ok && x.d.url) { window.location.assign(x.d.url); return }
        indo = false
        return cotar().then(function () { erro(x.d.erro || t('Something went wrong. Please try again.', 'Algo deu errado. Tente de novo.'), x.d.sign_in) })
      })
      .catch(function () { indo = false; desenhar(cot); erro(t('We could not reach the checkout. Please try again.', 'Não conseguimos abrir o pagamento. Tente de novo.')) })
  })

  cotar()
})()
