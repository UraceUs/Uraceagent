---
tipo: decisao
tipo_info: DECISION
data: 2026-09-25
fonte: pedido no chat do Claude Code, 25/09/2026 (conta urace@urace.us) — "reestruture todo o projeto do chase para que se adeque às novas diretivas para o SDR"; em 28/09/2026, no mesmo chat, o dono mandou levar em conta o relatório do time de vendas ("URACE — Meta e Kommo", 25/09) e escolheu os funis Urace → Comercial
responsavel: Italo Silveira
status: ativo
---

# D-2026-09-25 — Chase reorganizado como SDR

[[Decisoes]] · [[Projeto Chase]] · [[D-2026-08-27 - Descontinuar o Chase]]

## O que foi pedido

Reorganizar o código do Chase (`salesagent/`) pelas diretivas do SDR,
definidas na mesma semana: com uma pessoa só no atendimento, o Kommo passa a
separar o que é lead do que não é, e o comercial só olha lead. As diretivas
foram montadas e testadas antes em outro repositório (UraceUs/Chase-ai-BOT,
PR #1) e agora vivem aqui, em Python, dentro da ponte.

## Como ficou

- **Os funis da equipe: Urace → Comercial** (atualizado em 28/09, escolha do
  dono a partir do relatório do time de vendas). Urace › First Contact recebe
  tudo; as REGRAS 1 e 2 da equipe sobem o lead para Comercial › ENTRADA. O
  SDR não cria funil nem etapa: marca `nao_e_lead` no lixo antes da REGRA 1,
  resgata conversa enterrada em Cold Leads, avisa quando contato antigo de
  outro funil volta com sinal comercial e, no Comercial, só anda para frente.
  O "Novo funil" da primeira versão foi abandonado. A tabela "Quem move o
  quê" está em `salesagent/docs/sdr.md`.
- **Teste ponta a ponta de 28/09** (DMs do dono, ponte em observar): as três
  decisões saíram como previsto e nada foi escrito. Duas correções vieram
  dele, com o sim do dono no mesmo chat: (a) as REGRAS 1 e 2 só rodam para
  card que nasce em First Contact, então o SDR só segura para a REGRA 2 o
  card criado há menos de 15 min; card mais antigo com sinal comercial ele
  sobe para Comercial › ENTRADA com a tag DM; (b) `nao_e_lead` não vem mais
  de conversa de chat, só do nome do lead criado ou de e-mail.
- **Bots da equipe primeiro.** Onde a equipe já tem bot respondendo
  (Instagram, Messenger, WhatsApp, chat do site), a ponte não fala; só
  escala, como tarefa.
- **Janela de 24 h da Meta.** Follow-up que cairia fora dela não sai: vira
  tarefa para uma pessoa.
- **Triagem determinística** (`salesagent/sdr/`): código, e-mail de sistema,
  spam e fornecedor ficam fora da venda, com a tag `nao_e_lead`, que a equipe
  já usava à mão. Preço, agenda, conversão, pedido de pessoa e evento do site
  descem para venda.
- **Escalação com prioridade.** Alta chama agora. Média vira tarefa na fila
  do responsável único.
- **Guarda de estilo** no que sai para o lead: sem emoji, sem travessão, sem
  as frases proibidas do Chase.
- **Três níveis** em `SDR_MODO`: `observar`, `organizar` e `atender`.

## Travas

- **O padrão é `observar`:** decide e só registra no log. Não escreve no
  Kommo e não fala com lead. Assim nada aqui contraria
  [[D-2026-08-27 - Descontinuar o Chase]] (leads 100% humanos) nem
  [[D-2026-09-17 - O que a IA pode fazer, revisado pelo dono]] (etapa, tag e
  resposta no Kommo são do dono).
- **A IA não revoga decisão.** Subir para `organizar` ou `atender`, e religar
  o serviço `sales-bridge`, só com a palavra do dono. Quando ele disser, isto
  vira uma nova nota, que superará em parte a D-2026-08-27.
- O material de venda da era Chase segue no arquivo
  ([[D-2026-08-31 - Conhecimento da era Chase fica no arquivo]]). O SDR não
  afirma preço, horário, idade nem política que não tenha fonte confirmada:
  manda o link (G1) ou escala.

## O que ainda depende da palavra do dono

1. Ligar `organizar`, e depois `atender`.
2. Horário de atendimento humano. O valor atual é provisório: quarta a
   domingo, 9h–18h. A pista opera 8h–13h.
3. Qual robô responde em cada canal. Hoje respondem os bots da equipe; ligar
   o Chase num canal é tirar o canal de `CANAIS_COM_BOT_DA_EQUIPE` e desligar
   o bot da equipe ali. O Kommo não roda dois bots no mesmo lead.
3a. **Decidido pelo dono em 28/09**, no chat do Claude Code: o agente de IA
   do Kommo (*Agente qualificador de leads*) fica **sempre ligado** e é quem
   responde ao lead em Urace; o SDR segue sem responder nesses canais. E o
   SDR não precisa respeitar `nao_e_lead` posto antes num card que volta com
   sinal comercial: "IAs vão operar, não tem risco de erro humano".
3b. **Decidido pelo dono em 29/09** (depois do diagnóstico dos bots pela
   extensão): quem fala com o lead em Urace é **o menu do chatbot + o agente
   de IA**. O menu *URACE - Atendimento inicial DM* abre a conversa e grava o
   e-mail no card; o agente de IA responde o que fica fora do menu. As
   automações da Meta (Auto reply, Away e keywords de preço) continuam como
   primeiro toque. O diagnóstico mostrou que o agente estava desligado (22 de
   2.500 créditos usados) e que a voz "Instagram" nas conversas é a própria
   Meta. O SDR continua sem responder nesses canais.
3c. **Agente de IA, decidido pelo dono em 29/09:**
   - revela que é IA na 5ª mensagem, sem emoji, e nunca nega se o lead
     perguntar antes;
   - responde no idioma do lead;
   - não responde a 1ª mensagem de conversa nova (é da Meta e do menu) e
     responde o texto livre que vem depois, em qualquer conversa; sai a regra
     dos 7 dias;
   - o passo 6 da persona passa a citar os dois preços: $689 por dia de
     treino na Academy e $719 no Arrive and Drive.
   - o agente se chama **Chase** (a persona dizia "George"; dono, 29/09).
   - 30/09: o dono mandou deixar o agente **desligado**, com os ajustes
     salvos, pronto para ligar depois. Ligar = só a chave de status.
     Conferido pela extensão em 30/09: idioma "Match incoming message", as 3
     diretrizes novas, persona com Chase e preço só da PRICE RULES (2.978
     caracteres), frase do $689 corrigida na ação de contato e na fonte
     "Pergunta sobre budget", nenhum "George" nem $600 no agente.
   Aplicado no Kommo pela extensão, item por item, com o sim do dono.
4. ~~Quem é o responsável único~~ — **decidido pelo dono em 28/09**, no chat
   do Claude Code: URace Support (usuário 12209643 do Kommo). O Lucas não é
   usuário do Kommo. `KOMMO_RESPONSAVEL_ID=12209643` no `bridge.env`.
