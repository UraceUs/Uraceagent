/* Agenda do site novo (#148): a mesma disponibilidade da área do cliente, só que pública
 * (dias abertos e vagas, nada além). Escolheu kart, dia e turno → o botão leva para a
 * reserva (#164: sessão → conta → piloto → pagar) com tudo já marcado, e com a campanha de
 * onde a pessoa veio (utm_*, gclid, fbclid), para o marketing saber o que vendeu. Sem este
 * script, o botão leva para a mesma reserva, só que vazia.
 *
 * #236: o kart escolhido é o serviço do painel com esse nome, e o preço mostrado é o do painel (#50:
 * "já vai com aquele serviço e o preço que está lá"). "Add to cart" põe a sessão no carrinho do site,
 * que paga tudo junto no Stripe (o piloto é escolhido no carrinho, depois do login).
 *
 * #253 (dono, 15/10, com o serviço "teste" desativado no painel e a reserva travada no ar):
 * - o botão diz o que falta de verdade: sem dia, "Pick a day"; com dia e sem turno, "Pick a time";
 * - escolher o dia já escolhe o turno quando só um está aberto, e o turno de outro dia nunca fica
 *   marcado se não existe no dia novo; faltando o turno, os turnos ficam em destaque;
 * - painel sem serviço para esse kart: um aviso honesto com o contato, em vez de um botão morto. */
(function () {
  'use strict'
  var raiz = document.querySelector('.agenda')
  if (!raiz) return
  var api = raiz.getAttribute('data-api')
  var portal = raiz.getAttribute('data-portal')
  var grade = raiz.querySelector('.agenda-grade')
  var mesBox = raiz.querySelector('.agenda-mes')
  var titulo = raiz.querySelector('.agenda-titulo')
  var turnos = raiz.querySelector('.agenda-turnos')
  var aviso = raiz.querySelector('.agenda-aviso')
  var ir = raiz.querySelector('.agenda-ir')
  var resumo = raiz.querySelector('.agenda-resumo')
  var precoEl = raiz.querySelector('.agenda-preco')
  var porNoCarrinho = raiz.querySelector('.agenda-carrinho')
  var carrinhoOk = raiz.querySelector('.carrinho-ok')
  var indisponivel = raiz.querySelector('.agenda-indisponivel')
  var indisponivelTxt = raiz.querySelector('.agenda-indisponivel-txt')
  var servicos = [], comCarrinho = false, servicosOk = false
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
  function kart() {
    var k = document.querySelector('input[name="kart"]:checked')
    return k ? { nome: k.value, preco: Number(k.getAttribute('data-preco')) } : null
  }
  /** O serviço do painel deste kart: o único ativo com o nome do kart no nome. */
  function servico(k) {
    if (!k) return null
    var achados = servicos.filter(function (s) { return s.name.toLowerCase().indexOf(k.nome.toLowerCase()) >= 0 })
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

  function atualizar() {
    var k = kart()
    var s = servico(k)
    // #253: sem serviço nenhum ativo no painel, não há reserva online; com serviços, mas nenhum deste
    // kart, dá para reservar outra sessão na área do cliente — o aviso diz qual dos dois é o caso
    var semReservaOnline = servicosOk && !servicos.length
    var semEsseKart = servicosOk && !!servicos.length && !s
    if (indisponivel && indisponivelTxt) {
      indisponivelTxt.textContent = semReservaOnline
        ? 'Online booking is closed right now. Talk to us and we book your session for you:'
        : semEsseKart ? 'The ' + (k ? k.nome : 'kart') + ' is not open for online booking right now. Pick another kart above, or talk to us:' : ''
      indisponivel.hidden = !(semReservaOnline || semEsseKart)
    }
    resumo.textContent = (dia ? dataLonga(dia) + (periodo ? ' · ' + NOMES[periodo] : '') + ' · ' : '') + (k ? k.nome : '') + ' · per driver'
    precoEl.textContent = s ? usd(s.price) : k ? usd(k.preco) : ''
    var q = []
    if (dia) q.push('date=' + encodeURIComponent(dia))
    if (dia && periodo) q.push('period=' + encodeURIComponent(periodo))
    if (k) q.push('kart=' + encodeURIComponent(k.nome))
    CAMPANHA.forEach(function (c) { var v = daUrl.get(c); if (v) q.push(c + '=' + encodeURIComponent(v.slice(0, 120))) })
    ir.setAttribute('href', portal + (q.length ? '?' + q.join('&') : ''))
    // sem a agenda carregada (erro ou nada aberto), o botão continua levando à área do cliente
    var falta = !carregou ? null : !dia ? 'dia' : !periodo ? 'turno' : null
    var pronto = !falta
    ir.textContent = !carregou ? 'Book online' : pronto ? 'Continue to booking'
      : falta === 'dia' ? 'Pick a day to continue' : 'Pick a time to continue'
    if (pronto) ir.removeAttribute('aria-disabled'); else ir.setAttribute('aria-disabled', 'true')
    ir.hidden = semReservaOnline                      // nada ativo no painel: o botão não levaria a nada
    if (carregou) aviso.textContent = falta === 'turno' ? 'Now pick Morning or Afternoon.' : AVISO_PADRAO
    turnos.classList.toggle('falta', falta === 'turno')
    if (porNoCarrinho) {
      porNoCarrinho.hidden = !(comCarrinho && s && window.uraceCarrinho)
      porNoCarrinho.disabled = !(carregou && dia && periodo)
      porNoCarrinho.textContent = s && s.deposit ? 'Add to cart · ' + usd(s.price) + ' + ' + usd(s.deposit) + ' deposit' : 'Add to cart'
      ir.classList.toggle('btn-linha-escura', !porNoCarrinho.hidden)
    }
  }
  if (porNoCarrinho) porNoCarrinho.addEventListener('click', function () {
    var s = servico(kart())
    if (!s || !dia || !periodo || !window.uraceCarrinho) return
    if (!window.uraceCarrinho.por({ tipo: 'sessao', servico: s.id, data: dia, turno: periodo })) {
      carrinhoOk.textContent = 'Your cart is full.'
      return
    }
    carrinhoOk.textContent = 'Added to your cart. '
    var a = document.createElement('a'); a.href = '/cart/'; a.textContent = 'View cart and pay'
    carrinhoOk.appendChild(a)
    // #260: o `add_to_cart` da campanha (só catálogo, valor e moeda). Sem medição, não faz nada.
    if (window.uraceMedicao) {
      window.uraceMedicao.push({ event: 'add_to_cart', ecommerce: { currency: 'USD', value: Number(s.price) || 0,
        items: [{ item_id: 'sessao-' + s.id, item_name: s.name, item_category: 'sessao', price: Number(s.price) || 0, quantity: 1 }] } })
    }
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
  document.querySelectorAll('input[name="kart"]').forEach(function (r) { r.addEventListener('change', atualizar) })
  atualizar()

  var apiServicos = raiz.getAttribute('data-servicos')
  if (apiServicos) fetch(apiServicos, { credentials: 'same-origin', headers: { Accept: 'application/json' } })
    .then(function (r) { if (!r.ok) throw new Error(String(r.status)); return r.json() })
    .then(function (d) { servicos = d.services || []; comCarrinho = !!d.cart; servicosOk = true; atualizar() })
    .catch(function () { /* sem a lista do painel (rede): fica o "Continue to booking", sem aviso falso */ })

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
