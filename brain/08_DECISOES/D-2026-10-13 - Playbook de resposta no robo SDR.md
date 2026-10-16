# D-2026-10-13 — Playbook de resposta no robô SDR

fonte: pedido do dono no chat do Claude Code (sessão do SDR/Kommo), 13/10/2026:
"Use isso para poder ajustar como, o que e quando esse robô opera. Siga essas
instruções … como diretivas principais. Adapte todo o SDR para isso." Documentos
anexados: "URACE — Modo de Atendimento e Pipeline Comercial (13/10/2026)",
`PLAYBOOK_RESPOSTA.md` (versão da tarde de 13/10) e `ATENDIMENTO_13-10.md`
(registro do dia). Eles passam a ser a diretiva principal do robô que responde
no Kommo (bridge + agente OpenClaw `urace-sales`).

## O que mudou no robô

- **Persona** (`salesagent/instructions/urace-sales-agent.md`, v3): SDR, não
  closer. O Lucas fecha. Toda resposta é GANCHO → RESPOSTA → UMA PERGUNTA, e a
  qualificação vai em ordem: idade do piloto, experiência (nunca / aluguel /
  competição), objetivo. Abertura "Hi [FIRST NAME], Chase here from URACE."
- **Preço sai no chat**: a tabela de Arrive and Drive e Academy está na persona.
  A taxa de pista é sempre à parte e é dita junto. Nada fora da tabela: desconto,
  percentual de contrato, Racing Team, eventos e aluguel vão para o Lucas.
- **Quem é a pessoa decide o conteúdo**: cliente ativo não recebe venda; lead
  quente recebe a resposta na primeira linha e um passo; lead frio recebe uma
  pergunta; quem não é lead não recebe nada de venda.
- **Regra de um**: uma mensagem, um ativo. A persona tem a tabela de qual link
  ou vídeo mandar em cada situação, e o calendário (call de 15 min com o Lucas)
  só para quem já disse o que quer.
- **Datas**: quarta, sábado e domingo. O robô nunca confirma nem segura data.
- **Passagem para pessoa**: "Let me get Lucas on this. He replies right here,
  Monday to Friday, 8 am to 6 pm Orlando time."

## Objeção e muitas dúvidas viram call com o closer (pedido do dono, 13/10 à tarde)

Depois do teste no Instagram (o lead escalado disse "Consideraria se fosse mais
barato" e ouviu, em inglês, "Your question ... is with the team"), o dono pediu:
objeção, ou dúvida demais, vira oferta de call de 15 min com o Lucas, com o link
do calendário, para encaminhar ao closer seguindo o processo de venda.

- Persona: seção "When the next step is a call with Lucas": objeção de qualquer
  tipo (preço, tempo, distância, confiança, "vou pensar"), três ou mais
  perguntas, ou decisão real. Uma pergunta, um link, e `[[escalate]]` com o
  resumo para o Lucas. Nunca na primeira resposta.
- Ponte: objeção de preço e pedido de desconto (`regras.PALAVRAS["desconto"]`,
  que ganhou "está caro", "too expensive", "can't afford" etc.) recebem
  `holding.call_offer` em vez da espera genérica, inclusive em conversa já
  escalada. A pessoa continua sendo avisada. Link em `program-links.json`
  (`call_link`).
- A detecção de idioma da espera ganhou marcadores ("mais", "sim", "fosse",
  "isso", "então", "tá"): a frase do print saía em inglês.

## O que a ponte garante, mesmo se o modelo derivar

- `sdr/estilo.um_ativo`: primeira resposta a um lead sai sem link (o link e a
  chamada dele, "You can see it all here:", saem juntos); depois, no máximo um
  link por mensagem; no máximo uma pergunta por mensagem (fica a primeira). Cada
  corte vai para o log como `SDR estilo: ...`.
- A mesma guarda passa a valer no follow-up composto pelo agente (ele sai por
  `bots/run` e não passava pelo `send_to_lead`).
- `sdr/regras.NUNCA_DIZER` ganhou: "best regards", "i hope this message finds
  you well", "i hope this finds you well", "good to hear from you", "great
  question", "% off".
- `config/program-links.json`: 1-Day passa a ser
  `https://urace.us/services/arrive-and-drive`.
- `gates.get_price` não diz mais "nunca fale preço em número"; diz "só os
  números da tabela" e "link a partir da 2ª resposta".

Caso de referência dos testes: a resposta real que saiu no Instagram em 13/10
com link na primeira mensagem ("You can see it all here:
https://urace.us/product/go-kart-driving-experience/ How old is the driver?").

## Conflitos entre as fontes (decisão do dono pendente)

1. **Link do calendário**: o playbook usa `KBbHhXjoRMS6sbHv8`; o Modo de
   Atendimento usa `YSJSbZHNEGzVWRkC6`. A persona usa o do playbook.
2. **Academy**: o documento diz $2,756.90 / $689.23 (é o que foi faturado para a
   Daneyza, URACE-0032); `ratecard-2026.json` diz $2,756 / $689. A persona usa o
   do documento; a rate card não foi mexida.
3. **Dias**: o playbook diz quarta, sábado e domingo; o Modo de Atendimento
   descreve a janela da pista de quinta a domingo. O robô fala só quarta, sábado
   e domingo.
4. **Preço antes ou depois de qualificar**: a regra de 12/10 (agente do Kommo,
   D-2026-10-12) era preço só depois de idade e experiência. A de 13/10 é preço
   na primeira linha quando perguntam. Vale a de 13/10; o texto do agente de IA
   do Kommo (desligado) ficou desatualizado.
5. **Kart próprio**: a persona tem o preço ($500 o dia, $1,800 a Academy), mas a
   ponte continua escalando "own kart" antes do modelo (inspeção do kart é da
   gerência). O lead recebe a mensagem de espera e o Lucas responde.
6. Os descontos de contrato (4% / 8%) nunca são ditos ao cliente.
7. **Cadência**: o Modo de Atendimento fala de reativação (mínimo 7 dias, no
   máximo 2 tentativas, a 2ª muda de formato) e do loop de disparo por DDD,
   que são do disparo ativo, não do robô que responde. A cadência do robô não
   mudou: no Instagram/WhatsApp ela já é +2 h e +20 h e para (janela de 24 h
   da Meta); nos outros canais segue `FOLLOW_UP_MINUTOS`.

## O que não muda

Escopo de atuação (só a tag `teste-sdr` enquanto o dono não liberar), pausa por
conversa no Command Center, nível `atender` ligado pelo painel, regras de
escalação do B4, janela de 24 h da Meta.

## 14/10: tom URACE, sem nome do time, triagem curta (pedido do dono)

Teste no Instagram do Eduardo: o robô abriu com "Bom te ver de novo por aqui.
Pra seguir com a inspeção do kart e já marcar o treino com o Lucas..." e
mandou duas respostas para "Oi" + "Quanto custa?". O dono pediu:

- **Nunca citar o nome de alguém do time ao lead** (nem Lucas, nem Italo). O
  robô fala "URACE" ou "nosso time"; o treino é com a URACE. A call de 15 min é
  com o nosso time (o dono ou um dos nossos especialistas) para conversar sobre
  o desenvolvimento do piloto e os objetivos. Persona, oferta de call
  (`holding.call_offer`) e a frase de passagem foram reescritas.
- **Triagem curta**, mensagens curtas, amigável e respeitosa: quem é o piloto e
  que idade tem, já andou de kart de corrida, o que quer. Sempre tentando
  coletar o que falta, sem empurrar.
- **Contexto antigo não abre resposta.** A "inspeção do kart" veio da tabela
  `confirmations` (respostas do time em agosto), que entra em todo turno com o
  nome de quem respondeu. Agora entra como "a equipe confirmou", e a persona
  manda responder o que a pessoa perguntou agora. "Bom te ver de novo" e
  "good to see you again" entraram no `NUNCA_DIZER`.
- **Rajada vira uma resposta.** Mensagens do mesmo lead que chegam dentro da
  espera de 8 s entram numa fila; só a última responde, com o texto de todas.
- A "próxima ação sugerida" da ponte ainda mandava "obter a classificação
  A/B/C/D" e "conduzir ao fechamento"; agora segue a triagem e termina na
  oferta de call com o time.


## 14/10 (tarde): mensagens curtas, em balões separados (pedido do dono)

"Bloco grande o cliente não lê." Toda resposta sai em 2 a 4 mensagens curtas.

- Persona: cada linha é um balão; uma ou duas frases curtas por linha. Para
  "quanto custa": o preço, a taxa da pista à parte, e "É pra você ou pra outra
  pessoa, e qual a idade do piloto?". Depois segue coletando, uma coisa por vez.
- Ponte: `dividir_em_mensagens` quebra por linha e, se o modelo mandar um
  bloco, por frase (até 160 caracteres, no máximo 4 mensagens). No modo
  `json_reply` o bot mostra uma mensagem por disparo, então as seguintes ficam
  numa fila em `pending_followup_text` e o bot de entrega é disparado de novo,
  3 s depois, para cada uma. A guarda de estilo agora preserva as linhas.

## 14/10: cadência de follow-up quando o lead para de responder (pedido do dono)

- **~1h30 sem resposta:** sugere a call de 15 min com o nosso time, para
  conversar melhor e apresentar os programas, com o link do calendário. Tag
  `followup:1-call`.
- **23 h depois da nossa mensagem:** reativação curta ("faz um tempinho que a
  gente não conversa, seguimos à disposição, ficou alguma dúvida?"), sem link.
  Tag `followup:2-reativacao`.
- **Sem resposta depois disso:** a janela de 24 h da Meta fecha. O card ganha
  `followup:sem-resposta-24h` e uma tarefa para a pessoa (modelo aprovado,
  ligação ou perdido). O robô não fecha mais o card sozinho.
- O texto de cada toque é escrito pelo agente com a situação real do lead
  (o que perguntou, o piloto, o que falta), em 2 ou 3 linhas curtas.
- A margem da janela caiu de 60 para 30 min para o toque de 23 h caber.

## 14/10: "Testar o robô" no Command Center

Para ajustar o tom sem Instagram, sem lead de teste e sem comandos no VPS, a
página Robô SDR ganhou um chat de treino (OPERATOR+). A mensagem vai do painel
para a ponte (`POST /tools/playground`, com a chave do `bridge.env`), que roda
a mesma persona, as mesmas regras de rota (objeção, passar para a equipe, não é
lead) e a mesma guarda de estilo, e devolve os balões. Nada vai ao Kommo, nada é
enviado a ninguém, e as diretivas `[[...]]` só aparecem na tela. Cada conversa
de treino é uma sessão própria do OpenClaw (`playground-<id>`); "Nova conversa"
começa outra. Ideia tirada do repositório fazer-ai/agents (o playground deles);
migrar para aquela plataforma não faz sentido, porque ela não fala com o Kommo.

## 14/10 (noite): o que aproveitamos da pesquisa em repositórios

Pesquisa pedida pelo dono ("busque no github repos que possam nos ajudar a polir e finalizar"). Nenhum
projeto pronto serve de substituto (todos são email ou WhatsApp, nenhum fala com o Kommo), então só entram
as ideias que cabem no que já existe:

- **"Agora não" vira uma rota** (ideia das categorias de resposta do gelevanog/ai-sdr-agent). Lead que
  adia ("agora não", "not now", "depois eu falo") recebe duas linhas de agradecimento, o follow-up
  automático é cancelado, o card ganha `sdr:agora-nao` e uma tarefa para uma pessoa retomar em 7 dias.
  O card não é fechado. Só vale em mensagem curta e sem pergunta; "agora não sei a idade?" segue como
  pergunta, e desconto, reclamação ou pedido de pessoa continuam passando na frente.
- **Ritmo humano entre os balões** (ideia do delivery-queue do iPythoning/b2b-sdr-agent-template): o
  intervalo até o próximo balão era fixo (3 s); agora é 1,5 s mais 0,03 s por caractere, teto de 6 s e
  variação de 25%.
- **Bateria de conversas** (`salesagent/tests/test_sdr_bateria.py`, 34 casos, sem rede e sem modelo): o que
  o roteador decide para cada coisa que um lead escreve (do playbook e dos prints) e o que a guarda faz com
  as respostas erradas que já saíram. Também trava que a persona só cita Lucas e Italo na linha que
  proíbe citar.

Ficou de fora, de propósito: o juiz com IA (langwatch/scenario, deepeval) pede chave de API e não está
provado com Claude; áudio (faster-whisper) falta confirmar se o link do Kommo baixa; Langfuse só depois de
liberar o robô para todos os leads. O Click to Instagram Direct com janela de 7 dias é de um blog, não está
no changelog da Meta; não mexemos na cadência por isso.

## 15/10: revisão final (olhar de vendas e de engenharia)

Revisão pedida pelo dono para fechar o robô. O que mudou, na ordem de impacto:

**Vendas**
- **Quem está pronto, quem já corre e quem acha caro recebe a call, não a espera.** `SINAL_CONVERSAO` ("quero
  fechar", "como pago") e `PILOTO_COMPETIDOR` escalavam antes do modelo e o lead ouvia "sua pergunta está com a
  equipe", a mesma resposta que o dono recusou em 13/10. Agora cada motivo tem a sua oferta de call (`decisao`,
  `competidor`, `objecao`), em 3 a 4 balões curtos com o link sozinho no fim. A escalação e o aviso à equipe
  seguem iguais. Pedir uma pessoa e tema sensível continuam na frase de passagem.
- **A conversa tem linha de chegada.** Com idade, experiência e objetivo (ou um dia escolhido), o robô para de
  perguntar, manda a call e escala com o resumo. Persona e "próxima ação" da ponte dizem a mesma coisa.
- **Nada de follow-up de madrugada.** Entre 21h e 8h de Orlando o toque espera as 9h. Se as 9h já passam da janela
  de 24 h da Meta, sai às 20h30 da noite anterior; se nem isso dá, sai quando venceu. O toque nunca é perdido.
- **Nome do lead só se parecer nome de gente:** "055⚡ · Eduardo" vira "Eduardo"; @handle e número não entram.

**Persona (contradições que o modelo via a cada turno)**: a exceção do link no follow-up de 1h30 estava em dois
lugares e faltava em outros dois; o 2º toque "com link ou vídeo" contradizia o check-in sem link; `crm op=stage`
é bloqueado com o SDR ligado; `[[followup]]` de +3d/+7d cai fora da janela da Meta (só vale com data pedida pelo
lead); pedido de desconto agora aponta para a oferta de call.

**Engenharia**
- Nomes do time (Lucas, Italo) saem do contexto que o modelo lê (base de conhecimento, instruções do comercial,
  resultados de ferramenta). Não é filtro de saída: lead que se chama Lucas continua sendo chamado de Lucas.
- A ponte passa a registrar, sem o texto inteiro, as mensagens que SAÍRAM pelo webhook de conta
  (`saida_vista`: tipo, autor, origem). **Ainda não sabemos separar o robô, o Salesbot, uma automação e uma
  pessoa da equipe por esse payload**, então não há pausa automática: ela está no botão Pausar IA e na etapa
  ATENDIMENTO. Depois de um dia de logs dá para decidir se existe um sinal confiável.
- Teste do painel com limite de 12 por minuto por pessoa (cada teste é uma chamada ao modelo).
- `salesagent/tools/sdr_preflight.py` (confere nível, escopo de teste, bot de entrega, persona sincronizada,
  tamanho, links e Kommo, sem imprimir segredo) e `salesagent/docs/liberar-robo-sdr.md` (liberar, primeira hora,
  voltar atrás e a regra de ouro: antes de responder um lead à mão, mover para ATENDIMENTO ou Pausar IA).

**Fica como está, de propósito:** preços, números da cadência, tabela de links e a regra "sem link na 1ª resposta".
**Risco aberto antes de tirar `SDR_ATENDER_SO_TAG`:** cada balão é um disparo do bot de entrega; conferir 429 do
Kommo na primeira hora (roteiro) e a pessoa e o robô respondendo juntos (regra de ouro).

## 16/10 — Conferência do RAG
A busca no cofre indexava só `90_ARQUIVO/vendas-chase` (8 docs). Quatro deles traziam regra do Chase antigo que
contradiz o playbook de 13/10 e, entrando no bloco [SYSTEM] do turno, ganhavam da persona: menu A/B/C/D e "preço só
depois da classificação" (Qualificacao, aprendizado de 24/08), follow-up +2h/+24h/+3d/+7d (Follow-ups) e o script
"Italo handles program terms" (Objecoes). Passaram a `status: archived` e saem do índice na próxima indexação.
Ficam Politicas Comerciais, Pista e Check-in, Programas e Visao Geral. O aviso de "pouca informação" agora diz que
o que está nas instruções (preços, dias, endereço, idade, links) é base sólida, para o robô não responder
"vou confirmar" ao que já sabe. Pendente: um doc ativo de FAQ do SDR, escrito pelo dono, se quiser o RAG com conteúdo.

## 16/10 — Teste do comercial no "Testar o robô"
- **Academy**: a persona dizia "monthly, 4 sessions a month, no contract" com $2,756.90/$3,156.90. O Service
  Agreement (2026.2) tem **mínimo de 6 meses** (cláusula 2.1) e plano escalonado (1º mês 4 sessões, depois 2),
  e o preço do Academy está em conferência (contrato $9.649,15/6m contra a base). Até o time fechar a tabela, o
  robô **não diz preço do Academy**: fala do programa de 6 meses e oferece a call. A guarda corta $2,756/$3,156
  e "no contract"/"sem contrato" se o modelo escorregar. O $3.156,90 do 2 tempos vem da D-2026-08-31.
- **Idioma**: "É caro, faz por 2000 que fecho hoje?" saiu em inglês. O detector ganhou marcadores de objeção
  (desconto, muito, hoje, fecho, faz, agora, tem...) e a ponte passa a dizer ao modelo o idioma do turno. A
  contraproposta ("faz por X", "fecho hoje") passou a ser negociação: vai para a call.
- **Vídeo**: linha nova para quem compara escolas (vídeo "Who we are") e regra "se vídeo e página servem, manda
  o vídeo".
