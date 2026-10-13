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
