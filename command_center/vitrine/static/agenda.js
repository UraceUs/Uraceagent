/* Agenda do site novo (#148): a mesma disponibilidade da área do cliente, só que pública
 * (dias abertos e vagas, nada além). Escolheu kart, dia e turno → o botão leva para a
 * agenda da área do cliente com tudo já marcado. Sem este script, o botão leva para a
 * mesma agenda, só que vazia. */
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
  var SEMANA = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
  var NOMES = { manha: 'Morning', tarde: 'Afternoon' }
  var dias = {}, meses = [], mes = null, dia = null, periodo = null, cfg = null, carregou = false

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
  function dataLonga(iso) {
    return new Date(iso + 'T12:00:00').toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })
  }

  function atualizar() {
    var k = kart()
    resumo.textContent = (dia ? dataLonga(dia) + (periodo ? ' · ' + NOMES[periodo] : '') + ' · ' : '') + (k ? k.nome : '') + ' · per driver'
    precoEl.textContent = k ? usd(k.preco) : ''
    var q = []
    if (dia) q.push('date=' + encodeURIComponent(dia))
    if (dia && periodo) q.push('period=' + encodeURIComponent(periodo))
    if (k) q.push('kart=' + encodeURIComponent(k.nome))
    ir.setAttribute('href', portal + (q.length ? '?' + q.join('&') : ''))
    // sem a agenda carregada (erro ou nada aberto), o botão continua levando à área do cliente
    var pronto = !carregou || (dia && periodo)
    ir.textContent = !carregou ? 'Book in your account' : pronto ? 'Request this session' : 'Pick a day to continue'
    if (pronto) ir.removeAttribute('aria-disabled'); else ir.setAttribute('aria-disabled', 'true')
  }

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
        return function () { dia = x; periodo = null; desenharMes(); desenharTurnos(); atualizar() }
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
      aviso.textContent = 'Days in grey are closed or full. Times are Orlando time.'
      desenharMes()
      atualizar()
    })
    .catch(function () { aviso.textContent = 'We could not load the calendar. You can still pick your day after signing in.' })
})()
