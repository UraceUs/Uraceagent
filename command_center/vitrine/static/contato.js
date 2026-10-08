/* Formulários do site (#164): contato e pedido da loja. Com JavaScript, o envio é por fetch
 * e a resposta aparece na própria página; sem JavaScript, o formulário faz o POST normal e
 * volta para a página com ?sent=1. Nada aqui guarda dado da pessoa. */
(function () {
  'use strict'
  var forms = document.querySelectorAll('form[data-contato], form[data-pedido]')
  Array.prototype.forEach.call(forms, function (form) {
    var estado = form.querySelector('.form-estado')
    var botao = form.querySelector('button[type="submit"]')
    function diz(texto, classe) {
      if (!estado) return
      estado.textContent = texto
      estado.className = 'form-estado' + (classe ? ' ' + classe : '')
    }
    form.addEventListener('submit', function (ev) {
      if (!window.fetch) return                      // navegador antigo: POST normal
      ev.preventDefault()
      var dados = {}
      Array.prototype.forEach.call(form.elements, function (el) {
        if (el.name) dados[el.name] = el.value
      })
      if (form.hasAttribute('data-produto')) dados.produto = form.getAttribute('data-produto')
      if (botao) botao.disabled = true
      diz('Sending…')
      fetch(form.getAttribute('action'), {
        method: 'POST', credentials: 'omit',
        headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
        body: JSON.stringify(dados)
      }).then(function (r) { return r.json().catch(function () { return { ok: false } }) })
        .then(function (r) {
          if (r.ok) {
            form.setAttribute('data-enviado', '1')
            diz(form.hasAttribute('data-pedido')
              ? 'Thank you! We got your order request and will confirm availability, shipping and the total by email — nothing has been charged.'
              : 'Thank you! We got your message and will reply shortly, usually within one business day.', 'ok')
            form.scrollIntoView({ block: 'nearest' })
          } else {
            diz(r.erro || 'Something went wrong. Please try again or WhatsApp us.', 'erro')
            if (botao) botao.disabled = false
          }
        })
        .catch(function () {
          diz('Could not send right now. Please try again or WhatsApp us.', 'erro')
          if (botao) botao.disabled = false
        })
    })
  })
})()
