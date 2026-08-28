# Administrative AI — Descobertas (FASE 2/5, 27/08/2026)

> Levantamento READ-ONLY feito pelos MCPs conectados à sessão Claude.
> Nada foi criado/alterado nas plataformas.

## Conexões vivas (MCPs da sessão)

| Plataforma | Status | Identidade |
|---|---|---|
| Asana | ✅ autenticado | urace@urace.us (Italo Silveira), 2 workspaces (`1205117893189112`, `1205450084498489`) |
| Google Calendar | ✅ autenticado | 16 calendários visíveis |
| QuickBooks | ✅ autenticado | Company **URACE**, industry NAICS **711212** (Racetracks) |
| Gmail | ✅ conectado (conteúdo ainda não sondado) | — |
| Google Drive | ✅ conectado (não sondado) | — |

## Asana — projetos (workspace padrão)

| Projeto | GID | Tarefas (abertas/total) | Papel provável no Admin AI |
|---|---|---|---|
| **U-RACE** | 1205450093098920 | 37/1170 | operação/corridas — candidato a fonte do Workflow 1 |
| **ADM URACE** | 1205530439507169 | 87/1242 | administrativo geral |
| **ADM URace Workflow** | 1213585023616738 | 23/556 | provável casa dos TEMPLATES de processo |
| **Financeiro** | 1209321678013085 | 25/217 | invoices/pagamentos — Workflow 3 |
| CUSTOMERS SERVICE | 1205631592011879 | 41/52 | clientes |
| URace Drivers | 1212344952664712 | 17/19 | pilotos/clientes |
| Shipping Orders | 1215968721507536 | 37/40 | logística |
| Dealer overview | 1215642956993435 | 43/145 | dealers |
| SUITS | 1205661933760052 | 29/179 | equipamentos |
| Marketing / Social Media / Loja / Sponsorships / Business development / Canotops / Alphaline / Silveira Logistics (x2) / URACE AUTO | — | — | fora do MVP |

## Google Calendar — os que importam

| Calendário | ID | Uso no Admin AI |
|---|---|---|
| **Urace Race Calendar** | `c_739bbc...eafe4@group.calendar.google.com` | ALVO do Workflow 1 (corrida→evento) |
| URACE (principal) | `urace@urace.us` | practices and events |
| Urace Team | `c_classroomab7edc43@...` | equipe |
| CALENDÁRIO PESSOAL URACE-GETAVAN | `81b378...@group...` | compromissos das empresas |

(+8 calendários "Transferred from <ex-funcionário>" — legado; fora do MVP.)

## Implicações imediatas para os workflows

- **Workflow 1 (corrida)**: fonte provável = projeto U-RACE; destino = Urace
  Race Calendar. Chave de dedupe natural: GID da task Asana gravado no
  evento (extendedProperties) e vice-versa.
- **Workflow 3 (invoice)**: QuickBooks autenticado e respondendo; projeto
  Financeiro como espelho de estado no Asana.
- **Templates**: brief manda reutilizar — provável em "ADM URace
  Workflow"; PRÓXIMA SONDAGEM: listar tasks-modelo desse projeto.

## Sondagens pendentes (próxima rodada)

1. Estrutura real de uma "corrida" no U-RACE (campos, seções, naming).
2. Templates no ADM URace Workflow (nomes + GIDs).
3. Segundo workspace Asana (o que é?).
4. Gmail: labels e volume (sem ler conteúdo ainda).
5. QuickBooks: clientes/serviços existentes (qbo_contact_search, catalog).

## Anatomia de uma CORRIDA no Asana (sondado 27/08, fim do dia)

Fonte: projeto **U-RACE** → seção **RACES** (gid `1205450093098932`).

- Séries ativas: **AMR Karting Challenge 2026** (Rounds 6-11, Homestead) e
  **FLKC 2027** (calendário já lançado: Monticello, T4 Kartplex, Daytona,
  AMR Homestead). Naming: `<Série> Round N | (Local)` + `due_on`.
- Custom field: `Race = KART` (gid do campo `1213088541600529`).
- Notes da task: regra operacional ("Confirmation needed at least 15 days
  before the event, preferably fully organized 1 month prior") + campo
  "Event link:".
- Na mesma seção há tasks com NOME DE PILOTO e data de corrida (ex.: "Jude
  Cook", due 22-23/08) — provável participação de driver por corrida.

**O template operacional JÁ EXISTE como 25 subtarefas-padrão** (exemplo
real, Round 8 gid `1216270696569279`): Confirm Drivers · **Pre race
invoice** · Pit spot · Flights · Hotel · Track hours for practice · Event
schedule · Buy Tires · Specify Mechanic/Engine/Fuel Rule/Chassis · Assign
coaches (1:4) · Head staff · Send race info to WhatsApp group · Review
parts lists per driver · **After race invoice** · Pay race staff ·
Collect post-race client feedback · 4 Checklists FORMS · Post LineUp
Instagram · Create race financial sheet (Inflows & Outflows).

**Implicação direta**: os Workflows 1 (corrida→calendar) e 3 (invoice)
não precisam inventar processo — o processo é este template; o Admin AI
acompanha/preenche/relaciona estas subtarefas. "Pre/After race invoice"
são os pontos de encaixe do QuickBooks.

## FASE 1 — ENCERRADA (27/08, login validado pelo dono)

Causa (4 problemas empilhados) → correção → validação:
1. URL de IP cru anunciada pelo MOTD → usar `wss://urace-claw.duckdns.org`.
2. Token redigido (`__OPENCLAW_REDACTED__`) confundido com o real → doctor
   v3 lê o arquivo (`H2`: CLI redige na saída; config íntegra).
3. basic_auth bloqueando o handshake de WebSocket (1006) → rota `@ws` no
   Caddy (`fix_claw_ui_ws.sh`), token continua obrigatório.
4. Origin rejeitado pelo gateway em mode:local → `header_up Origin/Host`
   na mesma rota.
Mais: pareamento de dispositivo aprovado pelo dono
(`openclaw devices approve 67bf770e-...`). Login confirmado ("entrei").
Pendentes opcionais: rodar `remove_claw_ui_password.sh` (dono), revisar
`openclaw devices list`, rotacionar token que transitou por chats.

## FASE 2 — sondas finais (28/08, tudo read-only via MCP)

### ADM URace Workflow (projeto 1213585023616738) — o coração da operação recorrente

556 tarefas, 4 seções, membros Italo + Eduardo. É AQUI que o Admin AI se
encaixa: as cadências já existem e já estão escritas.

- **URace Daily Operations** — 2 tarefas/dia geradas por recorrência:
  - "Daily Operations Check (Morning -30min)", subtarefas atuais:
    [Team] Schedule (Practice) · Review track team assignments ·
    Urgent Financial Items · Customer Support.
  - "Daily Operations (During the day execute)": 1️⃣ Today's Priorities ·
    2️⃣ Track Operation · 3️⃣ Customer Support · 4️⃣ Finance Control.
- **Weekly Workflow (seg e sex)**:
  - "1️⃣ Financial Review - Race": bank statements · credit card ·
    weekly expenses · classify (Parts/Tires/Fuel/Logistics); meta
    declarada: "Offset expenses against parts sold to clients".
  - "2️⃣ Invoices" (2x/semana): "Create invoices for: Training sessions,
    Races, Parts, Services. Afterwards: ✔ Register in CRM ✔ Verify
    payment status" — é O workflow 3 (Preparação de Invoice) já
    documentado pela própria equipe.
- **Monthly Workflow (3–4h)**: "Sales Report" — [Eduardo] report
  (training/races/parts) · [Lara] comissões p/ Anabelly · [Lara]
  conciliação compras×vendas.
- **On-demand**: cartas p/ clientes (Eduardo), compra de peças com ciclo
  invoice→liberação→Ana p/ pagamento (Eduardo/Lara).

**Divisão de responsabilidades POR ESCRITO** (notes da tarefa diária):
- **Eduardo**: atendimento/operação diária, caixas urace@/support@,
  URace Store (incl. SUITS), cobrança de OS dos mecânicos, logística de
  corrida (passagens, hotel, carro, presença de mecânicos).
- **Lara**: planejamento e faturamento de corridas (schedule, pneus,
  pit-spot, invoices pré/pós), clientes Pro Team, conciliação
  compras×vendas, reembolsos de security deposit, conferência de
  pagamentos.
- Anabelly: pagamentos (recebe comissões e invoices liberadas).

**INCONSISTÊNCIA DOCUMENTADA (não corrigida): as recorrências PARARAM.**
Última "Daily Operations Check" gerada venceu em 03/07 (incompleta,
assignee Eduardo); último "Sales Report" venceu 01/08 (incompleto, "Em
andamento"). Hoje é 28/08 — quase 2 meses sem tarefas diárias geradas.
Ou a recorrência quebrou, ou o time abandonou o projeto. É pergunta de
negócio para o dono, e um alvo óbvio do Admin AI (gerar/cobrar cadência).

### Gmail — taxonomia de labels (mapa para o Workflow 2)

INBOX enxuta (32 threads) = triagem por labels funciona. Estrutura:
- `RACES/…` por série: National (SKUSA, USPKS, Star, Supernats, ROTAX,
  ROK Vegas, CKNA, IAME GN), Local FL (FLKC, AMR Homestead, Orlando
  Cup|BFO, FWT, WKA Daytona…), F4 (JFC, Lucas Oil, Fara).
- `Finances/…`: QuickBooks (727 threads), Square (5.607!), Receipt
  (2.170), Accounting, **"Pending Invoices ❗" (16 threads)** — fila
  manual de invoice pendente já existe como label.
- `Marketing & Sales/Comercial/…`: **"Formulario do site" (957
  threads)** = leads por e-mail; "Leads", "Leads por e-mail -
  acompanhar", CRM.
- `Team/…` (Eduardo, LARA, Samira, Anabelly, Ex-Employees/…),
  `Travels/…` (Flights 1.165, Hotels 732), `Platforms & Subscriptions/…`
  (ASANA 3.224 threads de notificação!), `URace Store/…`, `Suppliers`,
  `CORP/…`, `Suits`, `KartSport - Vantage Group`.
- Label `AWS VPS` (2 threads) — infra.

### QuickBooks — clientes e catálogo (URACE, realm 9341453113046421)

- **Vendas YTD 2026: $478.094,45 · 94 clientes ativos.** Top-5 concentra
  67,7%: Kenneth Savage ($164,5k, 34%), Donald Marron ($55,2k), Pablo
  Santiago ($54,1k), James Xikis ($37,7k), G TECH MOTORSPORTS ($12,1k).
  3 clientes com saldo negativo -$400 (reembolsos de deposit?—conferir).
- **Catálogo: 896 itens ativos** — 360 SERVICE / 536 NONINVENTORY (sem
  inventário rastreado no QB). Categorias por prefixo: Parts (361),
  Service (168), Rental (45), Parts IAME (39), OTK Parts (25), Electric
  (25), Clothes (21), Canotops (18), Engine parts (14), Karts (11),
  Fuel and Oil (11). Serviços = coaching (por idade/2T-4T), Summer Camp,
  Urace Academy, trackside support, shop labor (alignment, chassis,
  tires), Race Photos, Road trip cost, Flight Ticket.
- Confirma o desenho: invoice pré-corrida = serviços (coaching/track
  support/logística); pós-corrida = Parts consumidas + labor. Bate com a
  meta semanal "offset expenses against parts sold".

### Limite de sonda registrado
O MCP do Asana está preso ao workspace " COMMAND CENTER"
(1205450084498489); o segundo workspace (1205117893189112) não é
alcançável pelas ferramentas atuais — auditar via UI se necessário.

### CORREÇÃO DO DONO (28/08) — decisão de escopo
O projeto "ADM URace Workflow" (1213585023616738) NÃO será a base do
Admin AI — o dono descartou usá-lo (o que explica as recorrências
paradas desde julho: quadro abandonado, não bug). O que permanece válido
dali é só o CONTEÚDO descoberto (cadências, divisão Eduardo×Lara,
texto das tarefas de invoice) como referência de processo. A construção
será POR PARTES E POR APLICAÇÃO (Asana, Gmail, Calendar, QuickBooks,
Obsidian — uma de cada vez), não por um quadro central pré-existente.
