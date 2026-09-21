# Aplicação 2 — E-mail — MIGRADO

Este documento foi **migrado para o segundo cérebro** em 31/08/2026, na
construção do Cérebro Central. O conteúdo vive agora em:

- `brain/40_SISTEMAS/Taxonomia do Gmail.md` — a taxonomia real, com as contagens
- `brain/10_PROCESSOS/Triagem de e-mail.md` — a rotina
- `brain/40_SISTEMAS/Gmail.md`

O arquivo original fica aqui como registro do que foi levantado na
época. **A fonte de verdade é o vault** — se divergir, o vault vence.

---

<details>
<summary>Conteúdo original (28/08/2026)</summary>

# Aplicação 2 — E-mail (`urace@urace.us`)

Especificação ditada pelo dono em 28/08/2026. **Passo zero cumprido:** a
taxonomia abaixo foi lida da conta real, não presumida — 130+ marcadores
existentes, com contagem de threads para mostrar o que é usado de fato.

## Estado da caixa hoje

**36 threads na inbox, 5 não lidas.** Não é caos: é uma caixa trabalhada,
com uma taxonomia madura já construída. O trabalho da IA é **manter**,
não reinventar.

## A taxonomia real (o que cada marcador guarda)

### 🗞️ `wNews` — **1.943 threads** · o marcador de propaganda
É este que o dono citou. Newsletter, promoção, mala direta. Sub-níveis:
`wNews/Study` (839, cursos e conteúdo), `Study/Programa Imperium`,
`Study/Coach - Peaksports`, `wNews/George | Atendente`, `wNews/Italo| MAA`.
**Toda propaganda vai para cá** — é o que evita o acúmulo na inbox.

### 💰 `Finances` — o dinheiro
| Marcador | Threads | Guarda |
|---|---|---|
| `Finances/Square` | 5.607 | recebimentos Square |
| `Finances/Receipt` | 2.170 | comprovantes · `/Purchase refund` (18) |
| `Finances/Shopping` | 2.605 | compras · `/Amazon` (159) · `/Orlando Kart Center` (930) · `/Track Pass` (292) |
| `Finances/QuickBooks` | 727 | notificações do QB (invoice paga, recebida) |
| `Finances/Clover/Invoiss` | 282 | — |
| `Finances/Tolls` | 196 | pedágios |
| `Finances/Accounting` | 88 | contabilidade |
| **`Finances/Pending Invoices ❗`** | **16** | **a pagar / em aberto** — a fila que importa |
| `Finances/Auto Loan` · `/2025 Taxes` · `/Anderson_EB3` | — | — |

### 🏦 `Banks` — Bank of America (1.784) · American Express (645) ·
Robinhood (386) · PayPal (343) · Seacoast · Stripe · Venmo · Idea
Financial · `Financial Proposals` (112).

### 🏁 `RACES` — por série
`National/`: SKUSA (295) · USPKS (113) · Star Champions (107) ·
Supernats (48) · ROK Vegas (41) · ROTAX (32) · IAME USA GN (27) · CKNA.
`Local (FL)/`: FLKC (129) · Orlando Cup | BFO (80) · FWT (74) · AMR
Homestead Karting Challenge (16) · WKA Daytona · North Florida Kart Club.
`F4/`: JFC (31) · Fara (17) · Lucas Oil.

### 💼 `Marketing & Sales` — a porta de entrada comercial
`Comercial/Formulario do site` (**957** — leads do site) ·
`Comercial/Leads` (120) · `Comercial/Leads por e-mail - acompanhar` (87) ·
`Comercial/CRM` (45) · `Comercial/Canais | Social Media` (513) ·
**`Marketing & Sales/Partnership` (80)** — os parceiros que o dono pediu
cuidado especial · `Colina | Site e ADS` · `TKART` · `CapCut | Canva`.

### 📦 Operação de compra e envio
- **`Shipping Status` — 905 threads.** É **daqui** que sai a alimentação
  do quadro Shipping Orders do Asana.
- `URace Store/` : `Parts_Loja` (136) · `Purchase` (43) · `Shipped
  Orders` (36) · `Pending order` (5).
- `Suppliers` (338) · `/Stickers - Jake` · `/Mudflap`.
- `Platforms & Subscriptions/ebay` (260) · `/Orders` · `/Offer` · `/Case`;
  `/Alibaba` · `/Amazon` · `/ETSY`.

### 👕 `Suits` — 432 threads · `Suits/Homologação` (7, FIA 8877-2022)

### 🧑‍🤝‍🧑 `Team` — LARA (329) · Samira (151) · Anabelly (68) · Eduardo (33)
· `E-mails do Support` (87) · `Ex-Employees/MANU` (334) · `/Nathalia`.

### ✈️ `Travels` — Flights (1.165) · Hotels Reservation (732) ·
`Car rental/ Uber` (175) · `Flights/Refunds and Travel Credits` (61).

### 🎓 `Kart Racing School | Client talks` — 344 threads ·
`/Pro Team Urace` (44) · `/Insights`. Conversa direta com cliente.

### 📍 `LOC | Practice` — `Practice Orlando` (370) · `Practice Bushnell` (65)

### Outros
`Platforms & Subscriptions/ASANA` (3.224 notificações) ·
**`/Docusign` (54 — já existe e já é usado)** · Ecwid (438) · Dialpad
(355) · LegalShield · simplybook · magicJack · NordVPN · Google ·
Heroku · GitHub · `/AI` (70) · `CORP/` (AZ, Urace Autosales, Canotops,
Getavan, Silveira Logistics, Betim) · `ITALO` (527, pessoal: Casamento,
Hannah, `Pending email`) · `Resumes (CVs)` (508) · `KartSport - Vantage
Group` (36) · `Years 2019-2023/` (arquivo morto por ano) · `AWS VPS`.

## A rotina diária (proposta: 07h)

1. **Ler** cada thread nova da inbox — assunto, remetente e corpo.
2. **Interpretar** e classificar segundo a taxonomia acima.
3. **Aplicar o marcador.** Propaganda → `wNews`.
4. **Alimentar o Asana** quando for compra (ver abaixo).
5. **Criar rascunho** quando pedir resposta — nunca enviar.
6. **Perguntar** quando estiver em dúvida (regra dos primeiros dias).
7. **Relatar** o que fez, com contagem por marcador.

## Regras invioláveis

- 🚫 **A IA NUNCA ENVIA E-MAIL.** Só cria rascunho. Enviar é humano —
  mesma família da regra "a IA não envia a invoice".
- 🚫 **Não apagar, não arquivar sem instrução, não marcar spam.**
- ❓ **Na dúvida, perguntar.** Nos primeiros dias, generosamente.
- 🤝 **Tom das respostas:** a caixa recebe pedido de orçamento e mensagem
  de parceiro. Responder com calma e cordialidade — a relação vale mais
  que a eficiência. Nada de resposta seca ou automática demais.

## Alimentar o Shipping Orders (Asana) a partir do e-mail

Quando o e-mail for de compra nossa — confirmação do pedido, aviso de
envio, atualização de status, entrega —, a IA atualiza o quadro
**Shipping Orders** (`1215968721507536`):

| Campo do Asana | O que entra |
|---|---|
| **Nome da tarefa** | nome da peça / item comprado |
| `Supplier` | de onde comprou |
| `Order Number` | número do pedido |
| `Created at` | data da compra |
| `Tracking Number` | **link** de rastreio (regra do dono: sempre link) |
| `Status da ordem` | Order Created → Shipped → Arrived (+ quadro, ver `automacao-status-secao.md`) |
| descrição | previsão de entrega |

Dedupe pelo **número do pedido**: e-mail de atualização do mesmo pedido
**atualiza** a tarefa existente, nunca cria outra.

## Corrida no Asana → evento no Google Calendar

Corrida lançada na coluna RACES do U-RACE vira evento no calendário da
URACE (**Urace Race Calendar**, `c_739bbc…eafe4@group.calendar.google.com`)
com **as mesmas datas, o nome da corrida e o local**. Dedupe pelo `gid`
da tarefa do Asana guardado no evento.

## Como isso roda todo dia sem VPS

**Routine (tarefa agendada) do Claude Code:** dispara no horário, acorda
uma sessão com os mesmos conectores (Gmail, Asana, Calendar) e executa a
rotina. É o que torna o "todo dia às 7h" real sem token e sem servidor.

## Decisões fechadas pelo dono (28/08) — nada mais em aberto

| Pergunta | Decisão |
|---|---|
| Quais caixas | **`urace@urace.us` e `support@urace.us` desde já** |
| Etiquetou, arquiva? | **Só propaganda (`wNews`) sai da inbox.** Todo o resto fica visível, mesmo classificado |
| `Finances/Pending Invoices ❗` | **Conta a PAGAR** — o que a URACE deve. Cobrança emitida por nós não vai aqui |
| Rascunho para quê | **Lead/orçamento e cliente atual.** Parceria e financeiro o dono responde pessoalmente |

Duas leituras que essas respostas trazem, e que valem registrar:

- **Parceria fica fora do rascunho de propósito.** Foi justamente o
  assunto em que o dono pediu tom mais cuidadoso — e a conclusão dele é
  que esse é o tipo de e-mail que se responde pessoalmente. A IA
  classifica e para aí. Cuidado com a relação, na prática, virou *menos*
  automação, não mais.
- **Arquivar só propaganda** mantém a inbox como lista de pendências
  reais. A IA tira o ruído sem esconder decisão.

### Correção de uma leitura minha anterior

Eu havia dito que `Pending Invoices ❗` misturava contas a pagar e
cobranças a receber. Revendo os e-mails de lá — Goshen Land, Mammoth
Brothers, SXS Marketing, RacingJunk, Sampson Racing — **são todos contas
a pagar**. A pergunta era legítima, a caracterização de "misturado" não.
A regra do dono confirma: o marcador é de contas a pagar.

</details>
