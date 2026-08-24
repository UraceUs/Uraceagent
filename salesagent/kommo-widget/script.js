/**
 * Widget "Chase Bridge" — liga o Salesbot do Kommo à sales-bridge da URACE.
 *
 * v2 (24/08): fluxo em DOIS passos, seguindo o scaffold oficial do Kommo.
 * O passo 1 faz o widget_request e dá goto no passo 2; o passo 2 exibe
 * {{json.reply}} — o texto completo que a ponte devolve no campo `data` da
 * continuação. Assim a resposta chega como UMA mensagem com quebras de
 * linha, sem o limite de 80 caracteres que a validação do continue impõe
 * aos execute_handlers (descoberto no 1º teste ao vivo: 400 TooLong).
 * A ponte precisa estar em SALESBOT_DISPLAY=json_reply para casar com este
 * fluxo (bridge.env); o modo `balloons` continua existindo como fallback.
 *
 * v2 também remove data[talk_id]: o placeholder {{talk.id}} não resolve
 * nesta conta (chegava como texto literal).
 *
 * Padrão "re-trigger": o bot termina depois de responder; a próxima
 * mensagem do lead dispara o bot de novo (gatilho do Digital Pipeline).
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
          'https://urace-bridge.duckdns.org/kommo/hook';

        var stepRequest = {
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
                  contact_name: '{{contact.name}}',
                  contact_phone: '{{contact.phone}}',
                  from: 'widget'
                }
              }
            },
            // Executa depois que a ponte responde a continuação:
            { handler: 'goto', params: { type: 'question', step: 1 } }
          ],
          require: []
        };

        var stepShowReply = {
          question: [
            // {{json.reply}} = campo `reply` do `data` devolvido pela
            // ponte na continuação — a resposta completa do Chase, exibida
            // como uma única mensagem (sem limite de 80 chars).
            { handler: 'show', params: { type: 'text', value: '{{json.reply}}' } }
          ],
          require: []
        };

        return JSON.stringify([stepRequest, stepShowReply]);
      },

      destroy: function () {},
      onSave: function () { return true; }
    };

    return this;
  };
});
