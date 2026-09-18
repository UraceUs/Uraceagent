---
tipo: decisao
data: 2026-09-10
fonte: dono (chat, noite): "o principal é o chat"
tipo_info: DECISION
responsavel: Italo Silveira
status: ativo
---

# D-2026-09-10 — O chat do Kommo dentro do Command Center

**Dono:** *"Meu principal objetivo com ter o Kommo dentro do Command Center é
o chat… ele unifica Instagram, WhatsApp, Facebook, tudo ali dentro… preciso
do histórico do chat, o que foi enviado antes pela automação também… O funil
é importante, mas no momento quero focar no chat. Faz o que for preciso."*

## Como ficou

**Menu**: grupo *CRM · Kommo* com dois itens — **Chat** (`/crm/chat`, o
principal, com o contador de quem espera resposta) e **Funil de vendas**
(`/crm/funil`). O funil continua como está; clicar num lead lá abre a
conversa no chat.

**Chat**: caixa de entrada como a do Kommo — lista de conversas com nome,
canal (Instagram/Facebook/WhatsApp com cor e ícone), última mensagem e há
quanto tempo; quem espera resposta no topo com ●. Ao abrir: cabeçalho
enxuto (nome, canal, telefone e e-mail clicáveis, card do cliente se já for
cliente, "abrir no Kommo"), a etapa como seletor e as tags; a conversa em
balões; a caixa "Responder no chat do lead" (Ctrl+Enter envia) e a anotação
interna recolhida. Sem informação repetida.

## Como o chat entra e sai (o circuito provado em 24/08)

O Salesbot da conta tem um bloco de widget (o "Chase — responder ao lead",
já instalado) que, a cada **mensagem recebida**, faz `widget_request` para
`/ops/api/crm/hook?key=KOMMO_HOOK_KEY` (form-encoded) e **fica esperando**.
O painel guarda a mensagem, marca "espera resposta" e responde `{"ok":true}`
em menos de 2 s.

A **resposta humana** entra numa fila e sai pela continuação do bot
(`return_url`, modo `json_reply`: o bot mostra `{{json.reply}}`, o texto
inteiro de quem escreveu):

- se o bot ainda espera (o lead acabou de falar, < 50 s) → sai na hora;
- senão o painel dispara o bot (`POST /bots/{id}/run`), o bot volta ao hook
  **sem mensagem** e recebe a fila;
- se em 150 s nada saiu, a varredura marca **não entregue**, grava nota no
  lead ("enviar manualmente") e a tela mostra em vermelho. Nada some em
  silêncio.

Cada mensagem enviada fica com estado visível: *na fila* → *entregue* /
*não entregue*. A mensagem aparece no canal como do bot — limite do Kommo,
dito na tela.

## O histórico — o que dá e o que não dá

A API do Kommo **não entrega o texto** das mensagens dos canais nativos
(Instagram, Facebook, WhatsApp) — nem as antigas nem as que outra
automação mandou. O que ela entrega são os **eventos** de mensagem
recebida/enviada: lead, canal, direção e hora. O painel lê isso (30 dias,
a cada sincronia) e:

- monta a lista de conversas com o **canal certo** (origem de verdade) e
  "espera resposta" quando o cliente falou por último;
- mostra o histórico anterior como **uma marca compacta** ("3 mensagens
  pelo Instagram · 07/09 → 08/09 · o texto de antes do painel fica no
  Kommo — ler lá ↗"), sem encher a conversa de linhas repetidas.

A partir do momento em que o bot é ligado, **cada mensagem nova entra
inteira** e tudo o que sai do painel fica registrado: daí em diante o
painel é o histórico completo.

## Travas

Nada apaga; escrever é ato humano com `APLICAR` só na chamada e auditoria
(`crm.reply`, `crm.hook`, `crm.reply.failed`); hook só com chave (e JWT do
bot conferido quando `KOMMO_BOT_SECRET` existe); sem `KOMMO_BOT_ID` a
resposta é recusada em vez de fingida. Segredos em `~/.urace/kommo.env`,
que o serviço agora lê como `EnvironmentFile`; `KOMMO_HOOK_KEY` nasce no
deploy.

## Para ligar (na tela "Ligar o chat", só admin)

1. Salesbot **command-center** com um único bloco (o do widget) e a URL do
   hook copiada da tela.
2. *Sales funnel → Automate*: gatilho **mensagem recebida** → bot, em cada
   etapa onde o lead conversa.
3. `KOMMO_BOT_ID=<id do bot>` no `kommo.env`, reiniciar o serviço.
4. Mensagem de teste pelo Instagram.

Risco conhecido (era Chase): o gatilho tem **cooldown de 5 min por lead**;
se uma segunda mensagem no mesmo lead dentro de 5 min não disparar o bot, o
painel não a vê — a sincronia de eventos pega a marca, e o texto fica no
Kommo. É o primeiro ponto a observar no teste real.

Relacionado: [[D-2026-09-10 - Kommo dentro do Command Center]],
[[Kommo - o que da para fazer pelo Command Center]].
