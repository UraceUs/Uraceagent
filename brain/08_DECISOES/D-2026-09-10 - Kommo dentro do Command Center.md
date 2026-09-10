---
tipo: decisao
data: 2026-09-10
fonte: dono ("agora vamos colocar o kommo no command center")
tipo_info: DECISION
responsavel: Italo Silveira
status: ativo
---

# D-2026-09-10 — O Kommo entra no Command Center

O levantamento de 09/09 ([[Kommo - o que da para fazer pelo Command Center]])
virou aba. O dono pediu: inbox, responder, mudar o estágio, marcar tags,
ver informações de contato e **de onde a pessoa veio** (Instagram, Facebook,
WhatsApp), com a visão do funil.

## Como ficou

**Aba CRM · Kommo**: o funil em colunas, uma por etapa, lead por card com
nome, canal de origem (com cor e ícone), valor, tags, última mensagem e —
quando a pessoa já é cliente — o link para o card dela. Lead que falou por
último e ainda não teve resposta fica marcado *esperando resposta* e conta
no menu, como as waivers devolvidas.

**Abrir o lead** traz contato (e-mail e telefone clicáveis), origem, tags,
a etapa como **seletor** (mudar ali move no Kommo na hora) e a conversa.
Embaixo, duas caixas: **responder no canal** e **anotação interna**.

**Espelho + ao vivo**: a lista vem de `crm_leads`/`crm_messages` (rápida,
funciona mesmo com o Kommo fora do ar); ao abrir um lead o painel busca a
conversa ao vivo e guarda o que for novo. Sem token, a tela diz "não
conectado" e mostra só o que já tinha — nunca inventa lead.

**O webhook** (`/ops/api/crm/webhook`, com segredo em
`KOMMO_WEBHOOK_SECRET` no header `X-Urace-Secret`) põe a mensagem que
chega no Instagram/Facebook/WhatsApp na tela na hora, sem esperar a
sincronia — e marca o lead como esperando resposta.

## Travas (as mesmas de sempre)

- **Nada apaga**: não existe porta para apagar lead, contato, nota ou tag.
- **Escrever é ato humano**: mover etapa, marcar tag, anotar e responder
  são portas humanas do MCP, com `APLICAR` ligado **só naquela chamada**,
  RBAC de OPERATOR para cima e registro na auditoria (`crm.stage`,
  `crm.tags`, `crm.note`, `crm.reply`). A IA pode propor; quem manda a
  mensagem é gente.
- **Responder é honesto, em dois níveis**: a entrega usa o Salesbot da
  conta (caminho provado em 24-25/08 na era Chase), então a mensagem
  **aparece como do bot** e o gatilho tem cooldown de 5 min por lead. Sem
  `KOMMO_BOT_ID` o painel **recusa** responder e explica. E há um segundo
  detalhe que não pode ficar escondido: **o bot manda o que o roteiro dele
  manda**. Para o texto escrito no painel chegar ao cliente, o Salesbot
  precisa enviar um CAMPO do lead — o id vai em `KOMMO_CAMPO_RESPOSTA` e o
  painel grava o texto lá antes de disparar. Sem esse campo, a confirmação
  fica vermelha e avisa: o que foi escrito fica na nota do lead, mas quem
  escolhe o texto que o cliente lê é o bot. A anotação sempre funciona.
- **Segredo fora do repositório**: `~/.urace/kommo.env` (600) com
  `KOMMO_DOMAIN`, `KOMMO_TOKEN`, `KOMMO_BOT_ID`, `KOMMO_CAMPO_RESPOSTA` e
  `KOMMO_WEBHOOK_SECRET`.

## O que ainda depende da palavra do dono

1. Reaproveitar a integração privada "Chase Bridge (URACE)" (é o caminho
   mais curto) ou criar uma nova só para o Command Center.
2. O token longo daquela integração ainda vale? (basta a aba dizer
   CONNECTED depois de gravar o arquivo).
3. O funil do Chase (id 14316000), hoje sem uso, fica ou some? (o painel
   não apaga nada — some só se ele apagar no Kommo).
4. Resposta saindo como **bot** serve? Se não servir, o caminho é
   registrar canal próprio na Chats API (suporte do Kommo, 1 a 3 dias) e
   o WhatsApp teria de migrar.
5. Qual Salesbot entrega a resposta e **qual campo do lead ele envia**. O
   bot #9 (id 162247) da era Chase tem roteiro próprio, por etapa daquele
   funil: ligar `KOMMO_BOT_ID` nele sem antes trocar o roteiro faria o
   cliente receber a cópia do Chase, não o texto do painel. Enquanto isso
   não for conferido, o certo é deixar `KOMMO_BOT_ID` vazio — o painel
   recusa responder e todo o resto (funil, conversa, etapa, tags, nota)
   funciona.

Relacionado: [[Kommo - o que da para fazer pelo Command Center]], [[Projeto Chase]].
