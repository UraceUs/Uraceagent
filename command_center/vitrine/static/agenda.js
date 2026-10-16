/* Agenda do site novo (#148): a mesma disponibilidade da área do cliente, só que pública
 * (dias abertos e vagas, nada além).
 *
 * #236/#50: o preço que aparece é o do painel ("já vai com aquele serviço e o preço que está lá").
 *
 * #263 (dono, 15/10: "o mais lógico é ir com o produto que foi selecionado na mesma página que
 * selecionou a data e daí clicar no add to cart"): o serviço do kart é achado pela **chave**
 * (`site_kart`, igual e exata), nunca mais por "o nome do serviço contém o nome do kart" — foi o
 * casamento por nome que fez um serviço chamado "teste" passar por produto. O kart que o painel não
 * vende sai da página (o servidor já o deixa de fora; aqui sai na hora, se o painel mudou depois).
 *
 * #262 (dono, 15/10: "um caminho somente levando para o carrinho"): um botão só. Ele diz o que falta
 * escolher (dia, turno) e, com tudo escolhido, põe a sessão no carrinho e leva para o carrinho — onde
 * entrar ou criar a conta é obrigatório e o pagamento é só Stripe.
 *
 * #253: escolher o dia já escolhe o turno quando só um está aberto; o turno de outro dia nunca fica
 * marcado se não existe no dia novo; e painel sem serviço é um aviso honesto com o contato, nunca um
 * botão morto.
 *
 * #279 (dono, 15/10): o Lead and Follow é um add-on do dia de treino ($769, preço do painel) e vai junto
 * da sessão para o carrinho; o kart próprio é a 5ª opção, com o aviso de entregar o kart com 2 dias de
 * antecedência sempre à vista quando ele está escolhido. */
(function () {
  'use strict'
  var raiz = document.querySelector('.agenda')
  if (!raiz) return
  var api = raiz.getAttribute('data-api')
  var paraCarrinho = raiz.getAttribute('data-carrinho') || '/cart/'
  var grade = raiz.querySelector('.agenda-grade')
  var mesBox = raiz.querySelector('.agenda-mes')
  var titulo = raiz.querySelector('.agenda-titulo')
  var turnos = raiz.querySelector('.agenda-turnos')
  var aviso = raiz.querySelector('.agenda-aviso')
  var resumo = raiz.querySelector('.agenda-resumo')
  var precoEl = raiz.querySelector('.agenda-preco')
  var depositoEl = raiz.querySelector('.agenda-deposito')             // #282: o depósito com o ⓘ
  var depositoValor = raiz.querySelector('.agenda-deposito-valor')
  var porNoCarrinho = raiz.querySelector('.agenda-carrinho')
  var carrinhoOk = raiz.querySelector('.carrinho-ok')
  var indisponivel = raiz.querySelector('.agenda-indisponivel')
  var indisponivelTxt = raiz.querySelector('.agenda-indisponivel-txt')
  var lfBox = raiz.querySelector('.agenda-lf'), lfInput = raiz.querySelector('.agenda-lf input')
  var avisoKart = raiz.querySelector('.agenda-aviso-kart')
  var servicos = [], comCarrinho = false, servicosOk = false, lf = null
  var AVISO_PADRAO = 'Days in grey are closed or full. Times are Orlando time.'
  var SEMANA = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
  var NOMES = { manha: 'Morning', tarde: 'Afternoon' }
  var dias = {}, meses = [], mes = null, dia = null, periodo = null, cfg = null, carregou = false
  var CAMPANHA = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content', 'gclid', 'fbclid', 'ref']
  var daUrl = new URLSearchParams(window.location.search)

  function usd(n) { return '$' + Number(n).toLocaleString('en-US', { maximumFractionDigits: 2 }) }
  function hora(h) {
    var p = String(h || '').split(':'), hh = Number(p[0]), mm = p[1] || '00'
    if (isNaN(hh)) return ''
    return (hh % 12 || 12) + (mm !== '00' ? ':' + mm : '') + (hh < 12 ? ' AM' : ' PM')
  }
  function faixa(p) {
    if (!cfg) return ''
    return p === 'manha' ? hora(cfg.morning_start) + ' – ' + hora(cfg.morning_end)
      : hora(cfg.afternoon_start) + ' – ' + hora(cfg.afternoon_end)
  }
  function opcoes() { return [].slice.call(document.querySelectorAll('input[name="kart"]')) }
  function kart() {
    var k = document.querySelector('input[name="kart"]:checked')
    // #297: `nome` é o que o cartão mostra (o "nome no site" do painel); a chave continua a do kart
    return k ? { nome: k.getAttribute('data-titulo') || k.value, chave: k.getAttribute('data-kart') || k.value, preco: Number(k.getAttribute('data-preco')),
      proprio: k.getAttribute('data-proprio') === '1' } : null
  }
  /** A chave do kart, do jeito que ela é comparada: sem maiúscula e sem espaço à toa. */
  function chave(v) { return String(v == null ? '' : v).trim().replace(/\s+/g, ' ').toLowerCase() }
  /** O serviço do painel deste kart: o que tem esta chave em `site_kart`, e só quando é um só.
   *  Dois serviços com a mesma chave é ambíguo: ninguém escolhe no lugar da pessoa. */
  function servico(k) {
    if (!k) return null
    var c = chave(k.chave)
    if (!c) return null
    var achados = servicos.filter(function (s) { return chave(s.site_kart) === c })
    return achados.length === 1 ? achados[0] : null
  }
  function dataLonga(iso) {
    return new Date(iso + 'T12:00:00').toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })
  }
  /** Os turnos abertos no dia. */
  function turnosAbertos(iso) {
    var d = dias[iso]
    return ['manha', 'tarde'].filter(function (p) { return !!(d && d[p] && d[p].open) })
  }
  /** O turno que fica ao escolher o dia: o que já estava, se abre nesse dia; o único aberto; senão, nenhum. */
  function turnoDoDia(iso) {
    var abertos = turnosAbertos(iso)
    if (periodo && abertos.indexOf(periodo) >= 0) return periodo
    return abertos.length === 1 ? abertos[0] : null
  }

  /** #263: o kart que o painel não vende sai da página, e o preço de cada um é o do painel (#50).
   *  Só mexe depois de a lista do painel chegar: sem ela, a página fica como o servidor a mandou. */
  function karts() {
    if (!servicosOk) return
    var sobrou = null, escolhido = null
    opcoes().forEach(function (r) {
      var s = servico({ chave: r.getAttribute('data-kart') || r.value })
      var rotulo = r.closest('.kart')
      if (!s) { if (rotulo) rotulo.hidden = true; r.disabled = true; return }
      if (rotulo) rotulo.hidden = false
      r.disabled = false
      r.setAttribute('data-preco', String(s.price))
      var cel = rotulo && rotulo.querySelector('.kart-preco')
      if (cel) cel.textContent = usd(s.price)
      if (!sobrou) sobrou = r
      if (r.checked) escolhido = r
    })
    if (!escolhido && sobrou) sobrou.checked = true          // o kart que saiu não deixa a página sem escolha
  }

  /** #279: o Lead and Follow marcado, e só quando o painel vende (preço do painel). */
  function comLf() { return !!(lf && lfInput && lfInput.checked) }

  function atualizar() {
    var k = kart()
    var s = servico(k)
    if (lfBox) {
      // a caixa só fica na tela quando o painel vende o add-on; o preço é o dele (#50)
      if (servicosOk) lfBox.hidden = !lf
      var cel = lfBox.querySelector('.addon-preco')
      if (lf && cel) cel.textContent = '+' + usd(lf.price)
    }
    if (avisoKart) avisoKart.hidden = !(k && k.proprio)
    var extra = comLf() ? Number(lf.price) || 0 : 0
    // #253: sem serviço nenhum ativo no painel, não há reserva online; com serviços, mas nenhum deste
    // kart, dá para reservar outra sessão na área do cliente — o aviso diz qual dos dois é o caso
    var semReservaOnline = servicosOk && !servicos.length
    var semEsseKart = servicosOk && !!servicos.length && !s
    // #262: o pagamento do site é só Stripe. Stripe desligado é o mesmo que loja fechada: avisa com
    // o contato, em vez de deixar um botão que não levaria a nada.
    var semCheckout = servicosOk && !!s && !(comCarrinho && window.uraceCarrinho)
    // o servidor já mandou a página sem kart nenhum e com o aviso no lugar da lista: não repetir
    if (indisponivel && indisponivelTxt && opcoes().length) {
      indisponivelTxt.textContent = semReservaOnline
        ? 'Online booking is closed right now. Talk to us and we book your session for you:'
        : semEsseKart ? 'The ' + (k ? k.nome : 'kart') + ' is not open for online booking right now. Pick another kart above, or talk to us:'
          : semCheckout ? 'Online checkout is closed right now. Talk to us and we book your session for you:' : ''
      indisponivel.hidden = !(semReservaOnline || semEsseKart || semCheckout)
    }
    resumo.textContent = (dia ? dataLonga(dia) + (periodo ? ' · ' + NOMES[periodo] : '') + ' · ' : '') + (k ? k.nome : '')
      + (comLf() ? ' + Lead and Follow' : '') + ' · per driver'
    precoEl.textContent = s ? usd(Number(s.price) + extra) : k ? usd(k.preco + extra) : ''
    if (depositoEl) {
      var dep = s ? Number(s.deposit) || 0 : 0
      depositoEl.hidden = !dep
      depositoValor.textContent = dep ? usd(dep) : ''
    }
    // sem a agenda carregada (erro, ou nada aberto), o botão continua pedindo o dia
    var falta = !carregou || !dia ? 'dia' : !periodo ? 'turno' : null
    if (carregou) aviso.textContent = falta === 'turno' ? 'Now pick Morning or Afternoon.' : AVISO_PADRAO
    turnos.classList.toggle('falta', falta === 'turno')
    // #262: um botão só. Ele conta o que falta e, pronto, leva ao carrinho.
    var pode = !!(s && comCarrinho && window.uraceCarrinho)
    porNoCarrinho.hidden = !opcoes().length || (servicosOk && !pode)
    porNoCarrinho.disabled = !(pode && !falta)
    if (porNoCarrinho.disabled) porNoCarrinho.setAttribute('aria-disabled', 'true')
    else porNoCarrinho.removeAttribute('aria-disabled')
    porNoCarrinho.textContent = falta === 'dia' ? 'Pick a day to continue'
      : falta === 'turno' ? 'Pick a time to continue'
        : !s ? 'Add to cart'
          : 'Add to cart · ' + usd(Number(s.price) + extra) + (s.deposit ? ' + ' + usd(s.deposit) + ' deposit' : '')
  }
  porNoCarrinho.addEventListener('click', function () {
    var s = servico(kart())
    if (!s || !dia || !periodo || !window.uraceCarrinho) return
    var querLf = comLf()
    if (!window.uraceCarrinho.por({ tipo: 'sessao', servico: s.id, data: dia, turno: periodo, lead_follow: querLf })) {
      carrinhoOk.textContent = 'Your cart is full. '
      var ver = document.createElement('a'); ver.href = paraCarrinho; ver.textContent = 'View cart and pay'
      carrinhoOk.appendChild(ver)
      return
    }
    // #260: o `add_to_cart` da campanha (só catálogo, valor e moeda), ANTES de sair da página.
    // Sem medição, não faz nada.
    if (window.uraceMedicao) {
      var itensMed = [{ item_id: 'sessao-' + s.id, item_name: s.name, item_category: 'sessao', price: Number(s.price) || 0, quantity: 1 }]
      if (querLf) itensMed.push({ item_id: 'addon-' + lf.id, item_name: lf.name, item_category: 'addon', price: Number(lf.price) || 0, quantity: 1 })
      window.uraceMedicao.push({ event: 'add_to_cart', ecommerce: { currency: 'USD',
        value: (Number(s.price) || 0) + (querLf ? Number(lf.price) || 0 : 0), items: itensMed } })
    }
    carrinhoOk.textContent = 'Added to your cart. Taking you there…'
    // a campanha de onde a pessoa veio segue para o carrinho (utm_*, gclid, fbclid)
    var q = []
    CAMPANHA.forEach(function (c) { var v = daUrl.get(c); if (v) q.push(c + '=' + encodeURIComponent(v.slice(0, 120))) })
    window.location.assign(paraCarrinho + (q.length ? '?' + q.join('&') : ''))
  })

  function desenharTurnos() {
    turnos.textContent = ''
    if (!dia) { turnos.hidden = true; return }
    var d = dias[dia]
    ;['manha', 'tarde'].forEach(function (p) {
      var info = d[p], b = document.createElement('button')
      b.type = 'button'; b.className = 'agenda-turno'; b.setAttribute('aria-pressed', String(periodo === p))
      b.disabled = !info.open
      b.innerHTML = '<span></span><small></small>'
      b.firstChild.textContent = NOMES[p]
      b.lastChild.textContent = info.open ? faixa(p) + ' · ' + info.spots + (info.spots === 1 ? ' spot left' : ' spots left') : 'Not available'
      b.addEventListener('click', function () { periodo = p; desenharTurnos(); atualizar() })
      turnos.appendChild(b)
    })
    turnos.hidden = false
  }

  function desenharMes() {
    grade.textContent = ''
    SEMANA.forEach(function (s) { var x = document.createElement('span'); x.className = 'ds'; x.textContent = s; grade.appendChild(x) })
    var a = Number(mes.slice(0, 4)), m = Number(mes.slice(5, 7))
    var primeiro = new Date(a, m - 1, 1).getDay(), total = new Date(a, m, 0).getDate()
    for (var i = 0; i < primeiro; i++) grade.appendChild(document.createElement('span'))
    for (var n = 1; n <= total; n++) {
      var iso = mes + '-' + (n < 10 ? '0' : '') + n, d = dias[iso]
      var aberto = !!(d && (d.manha.open || d.tarde.open))
      var b = document.createElement('button')
      b.type = 'button'; b.className = 'agenda-dia' + (aberto ? ' aberto' : '')
      if (aberto && Math.max(d.manha.spots, d.tarde.spots) <= 1) b.className += ' poucas'
      b.textContent = n; b.disabled = !aberto
      b.setAttribute('aria-pressed', String(dia === iso))
      b.setAttribute('aria-label', dataLonga(iso) + (aberto ? ', available' : ', not available'))
      if (aberto) b.addEventListener('click', (function (x) {
        // #253: o turno de outro dia não fica marcado se não abre neste; um só turno aberto já vem escolhido
        return function () { dia = x; periodo = turnoDoDia(x); desenharMes(); desenharTurnos(); atualizar() }
      })(iso))
      grade.appendChild(b)
    }
    titulo.textContent = new Date(mes + '-15T12:00:00').toLocaleDateString('en-US', { month: 'long', year: 'numeric' })
    var i0 = meses.indexOf(mes)
    mesBox.querySelector('[data-ir="-1"]').disabled = i0 <= 0
    mesBox.querySelector('[data-ir="1"]').disabled = i0 >= meses.length - 1
  }

  mesBox.addEventListener('click', function (ev) {
    var b = ev.target.closest('[data-ir]')
    if (!b || b.disabled) return
    mes = meses[meses.indexOf(mes) + Number(b.getAttribute('data-ir'))]
    desenharMes()
  })
  opcoes().forEach(function (r) { r.addEventListener('change', atualizar) })
  if (lfInput) lfInput.addEventListener('change', atualizar)
  atualizar()

  var apiServicos = raiz.getAttribute('data-servicos')
  if (apiServicos) fetch(apiServicos, { credentials: 'same-origin', headers: { Accept: 'application/json' } })
    .then(function (r) { if (!r.ok) throw new Error(String(r.status)); return r.json() })
    .then(function (d) { servicos = d.services || []; lf = d.lead_follow || null; comCarrinho = !!d.cart; servicosOk = true; karts(); atualizar() })
    .catch(function () { /* sem a lista do painel (rede): a página fica como o servidor a mandou */ })

  fetch(api, { credentials: 'omit', headers: { Accept: 'application/json' } })
    .then(function (r) { if (!r.ok) throw new Error(String(r.status)); return r.json() })
    .then(function (d) {
      cfg = d.config
      d.dias.forEach(function (x) { dias[x.date] = x })
      meses = d.dias.reduce(function (acc, x) { var m = x.date.slice(0, 7); if (acc.indexOf(m) < 0) acc.push(m); return acc }, [])
      var primeiro = d.dias.filter(function (x) { return x.manha.open || x.tarde.open })[0]
      if (!primeiro) { aviso.textContent = 'No dates open for booking right now. Please check back soon or talk to us.'; return }
      mes = primeiro.date.slice(0, 7)
      carregou = true
      mesBox.hidden = false
      aviso.textContent = AVISO_PADRAO
      desenharMes()
      atualizar()
    })
    .catch(function () { aviso.textContent = 'We could not load the calendar. You can still pick your day after signing in.' })
})()
