---
tipo: sistema
tipo_info: CONTEXT
data: 2026-09-09
fonte: docs da era Chase (salesagent/docs/kommo-circuit-setup.md, CONSOLIDACAO.md, config/kommo-pipeline.json) + API v4 do Kommo
responsavel: Italo Silveira
status: em estudo (sem ação até o dono decidir)
---

# Kommo — o que dá para fazer pelo Command Center

[[Gmail]] · [[Projeto Chase]] · [[Administrative AI]]

Pedido do dono (09/09): aba Kommo no painel com inbox, resposta, estágio,
tags, contato, origem do lead e visão do funil. **Nenhuma ação tomada;
só levantamento.** Continua em 10/09.

## O que já existe da era Chase (reaproveitável)
- Integração privada **"Chase Bridge (URACE)"** instalada e ativa na conta
  `urace.kommo.com`; token longo em `~/.urace/kommo.env` (`KOMMO_TOKEN`,
  `KOMMO_DOMAIN`, `KOMMO_BOT_SECRET`). Validade do token a conferir.
- **Plano Advanced** (confirmado 21/08) — libera Salesbot + `widget_request`.
- **Salesbot #9 (id 162247)** com gatilho "mensagem recebida", um por
  etapa do funil do Chase; provado ponta a ponta com lead real do
  **Instagram** em 24/08. Disparo espontâneo por API
  (`POST /api/v4/bots/{id}/run`, `entity_type: "leads"`) provado em 25/08.
- Funil real **"Sales funnel"** (id 9903543) com 13 etapas lidas da
  conta em `salesagent/config/kommo-pipeline.json`; existe também o funil
  do Chase (id 14316000), criado em 17/08, hoje sem uso.
- Risco conhecido: gatilho com **cooldown de 5 min por lead** pode não
  disparar na segunda mensagem seguida.
- Pendência antiga: rotacionar o client secret (passou pelo chat em 24/08).

## Por capacidade
| Capacidade | Dá? | Como | Ressalva |
|---|---|---|---|
| Ver o funil e mover de etapa | Sim | API v4 leads/pipelines | — |
| Tags, notas, tarefas, responsável | Sim | API v4 | — |
| Dados de contato (e-mail, telefone, campos) | Sim | API v4 contacts | — |
| Origem do lead (Instagram/Facebook/WhatsApp) | Sim | canal da conversa / campo de origem | link de anúncio/UTM só se o formulário capturou |
| Ler as mensagens que chegam | Sim, a partir da ativação | Salesbot "mensagem recebida" → webhook no painel | histórico anterior não vem pela API |
| Responder pelo painel (canais nativos) | Sim | Salesbot disparado por API + widget (caminho do Chase) | sai como mensagem do bot; cooldown 5 min |
| Responder como canal próprio (Chats API) | Sim | registrar canal via suporte (1–3 dias) | WhatsApp teria de migrar; Instagram/Facebook seguem nativos |
| Modelos oficiais do WhatsApp, chamadas, anexos ricos | Não/limitado | — | ficam no Kommo |
