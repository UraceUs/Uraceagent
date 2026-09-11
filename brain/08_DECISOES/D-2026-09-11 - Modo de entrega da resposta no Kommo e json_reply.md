---
tipo: decisao
data: 2026-09-11
fonte: teste ao vivo do dono pelo WhatsApp
responsavel: Italo Silveira
status: ativo
---

# D-2026-09-11 — O modo de entrega da resposta no Kommo é `json_reply`

[[Kommo - o que da para fazer pelo Command Center]] · [[D-2026-09-10 - O chat do Kommo dentro do Command Center]]

## O que aconteceu

O dono testou ponta a ponta: mandou "Teste" do WhatsApp dele para o WhatsApp da
URACE e respondeu pelo painel. **O circuito inteiro funcionou** — o Kommo
recebeu, o Salesbot disparou, o hook do painel respondeu e a mensagem voltou
para o celular dele. Mas o que chegou foi o texto literal `{{json.reply}}`.

Fica provado, de passagem, que **o WhatsApp está de pé**. O que caiu é só
Instagram e Facebook.

## A causa

Existem dois modos de entregar a resposta na continuação do Salesbot, e cada
lado estava num deles:

| Lado | Estava em | O que faz |
|---|---|---|
| Salesbot no Kommo | `json_reply` | bloco "enviar mensagem" com o texto `{{json.reply}}` |
| Command Center | `balloons` (padrão do código) | devolve `execute_handlers` com balões |

Em `balloons` a variável `json.reply` nunca é preenchida, então o Kommo envia o
molde como se fosse texto. Não é erro de código: é desencontro de configuração.

## A decisão

`KOMMO_MODO_ENTREGA=json_reply` em `~/.urace/kommo.env`. Alinha o painel ao bot
que já existe, sem tocar no Salesbot.

Se algum dia o bot for refeito **sem** o bloco `{{json.reply}}`, o modo volta a
ser `balloons` — que é o provado com lead real do Instagram em 24/08.

## Lição do terminal, de novo

O bloco de comandos com barra de continuação (`\`) **quebrou** neste terminal:
o paste multi-linha virou `-bash: syntax error near unexpected token '&&'`. É a
terceira vez (ver a chave RSA do DocuSign em [[2026-09-01]]). Regra: **comando
para o VPS vai sempre em UMA linha, separado por `;`**, nunca com `\`.
