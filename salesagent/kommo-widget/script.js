/**
 * Widget "Chase Bridge" — liga o Salesbot do Kommo à sales-bridge da URACE.
 *
 * Registra o bloco "Chase" no designer do Salesbot. Ao salvar o bot, gera o
 * fluxo que faz widget_request ao endpoint /kommo/hook da ponte, enviando a
 * mensagem do lead e o contexto. A resposta do Chase volta pelo return_url
 * (a ponte chama a API de continuação) e o Salesbot a exibe no chat.
 *
 * Padrão "re-trigger": o bot termina depois de responder; a próxima
 * mensagem do lead dispara o bot de novo (gatilho de mensagem recebida no
 * Digital Pipeline). Sem loop interno — mais simples e mais robusto.
 *
 * Docs: https://developers.kommo.com/docs/private-chatbot-integration
 */
define(['jquery'], function ($) {
  return function CustomWidget() {
    var self = this;

    this.callbacks = {
      settings: function () {},
      init: function () { return true; },
      bind_actions: function () { return true; },
      render: function () { return true; },

      onSalesbotDesignerSave: function (_handler_code, params) {
        // URL digitada no bloco do designer (campo "text"); o fallback só
        // existe para não salvar um bot quebrado se o campo vier vazio.
        var hookUrl = (params && params.text) ||
          'https://bridge.urace.us/kommo/hook';

        var step = {
          question: [
            {
              handler: 'widget_request',
              params: {
                url: hookUrl,
                data: {
                  // {{message_text}} é o placeholder oficial da mensagem
                  // do cliente; os demais dão contexto pro CRM da ponte.
                  message: '{{message_text}}',
                  lead_id: '{{lead.id}}',
                  talk_id: '{{talk.id}}',
                  contact_name: '{{contact.name}}',
                  contact_phone: '{{contact.phone}}',
                  from: 'widget'
                }
              }
            }
          ],
          require: []
        };

        return JSON.stringify([step]);
      },

      destroy: function () {},
      onSave: function () { return true; }
    };

    return this;
  };
});
