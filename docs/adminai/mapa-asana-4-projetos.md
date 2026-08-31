# Mapa do Asana — os 4 projetos — MIGRADO

Este documento foi **migrado para o segundo cérebro** em 31/08/2026, na
construção do Cérebro Central. O conteúdo vive agora em:

- `brain/40_SISTEMAS/Asana.md` — projetos, GIDs, seções e campos
- `brain/13_PROBLEMAS/` — as inconsistências viraram problemas rastreados

O arquivo original fica aqui como registro do que foi levantado na
época. **A fonte de verdade é o vault** — se divergir, o vault vence.

---

<details>
<summary>Conteúdo original (28/08/2026)</summary>

# Mapa do Asana — os 4 projetos do Administrative AI

Levantamento feito ao vivo em 28/08/2026, **100% leitura** (nenhuma
escrita, nenhuma tarefa criada ou alterada). Workspace ` COMMAND CENTER`
(`1205450084498489`). Este documento é a base factual da automação: tudo
aqui foi lido da fonte, nada foi presumido.

## Permissões por projeto (decisão do dono, 28/08)

| Projeto | GID | Acesso do Admin AI |
|---|---|---|
| U-RACE | `1205450093098920` | ler agora · escrever depois de validado |
| SUITS | `1205661933760052` | ler agora · escrever depois de validado |
| Shipping Orders | `1215968721507536` | ler agora · escrever depois de validado |
| ADM URACE | `1205530439507169` | **SOMENTE LEITURA — não criar, não alterar nada** |

Ordem de trabalho definida pelo dono: U-RACE / SUITS / Shipping Orders
primeiro; **pedidos que chegam por e-mail ficam por último**; ADM URACE
só depois que Shipping Orders estiver funcionando.

---

## 1. U-RACE — o calendário de serviços e corridas

**Seções (os "quadros"):** RACES · Finished Services · **TUESDAY ·
WEDNESDAY · THURSDAY · FRIDAY · SATURDAY · SUNDAY** · 🗓️ Pending
Reschedule · Luis tasks · Matt tasks

Os dias da semana são o calendário operacional: cada serviço vendido
vira uma tarefa que é **movida para o quadro do dia** em que acontece.
1.170 tarefas (37 abertas). 9 membros.

**Campo personalizado:** `Race` (enum, gid `1213088541600529`) →
KART · F4 · Practice OKC · Practice Bushnell · TRACK CLOSED

### Modelo de tarefa: SERVIÇO (12 subtarefas)

Nome no padrão `{Piloto}_{Serviço}_{Categoria} [n/total]`
(ex.: `Jayden Lago_Professional Coaching_4T [1/1]`).

Descrição (bloco semi-estruturado que precisa ser preenchido):
```
Service Dates for this Month: 07/30
Driver's name / Date of Birth / Age / Height / Weight / Waist
Karting Experience
----------------------------------------
Responsible Name / Email / Phone   (responsável legal)
----------------------------------------
Invoice link: https://connect.intuit.com/...   Price: $719,00
Security deposit: https://connect.intuit.com/...  Price: $400
```

As 12 subtarefas padrão (ciclo completo do serviço):
1. Price + Payment Links (Service)
2. Payment has been completed (invoice)?
3. Security Deposit sent?
4. Signed waiver?
5. Security Deposit paid?
6. Send Driver Pass/Registration Link to the client
7. Service Order
8. COACH | Feedback about the driver/session
9. Return Security Deposit
10. After-Sales | Send feedback forms and invite to the next session
11. Checklist Coach
12. Checklist Mechanic

**O que se preenche/altera ao usar o modelo:** `due_on` = data do
serviço · `assignee` = responsável (hoje Luis Barros nos practices) ·
campo `Race` · **mover para a seção do dia da semana** · preencher o
bloco de descrição · colar os links de invoice e de security deposit.

### Modelo de tarefa: CORRIDA (25 subtarefas)

Fica na seção RACES; já mapeado em `app-asana-corridas.md`. Inclui
Pre race invoice e After race invoice, e a regra do projeto:
confirmação ≥15 dias antes do evento, organizado 1 mês antes.
(Corridas antigas têm 19 subtarefas — template mais velho.)

---

## 2. SUITS — pedidos de macacão (equipe e clientes)

179 tarefas (29 abertas). Membros: Italo, Anabelly, Eduardo.
**Seções:** Order · Standby · Checklist para o pedido de macacão ·
SUIT LEADS · Fornecedores · Seleção de fornecedores.

Cada pedido é uma tarefa com o **nome do cliente** (ex.: `Michael
Fuller`, `Alexander Savage (2 suits)`).

**Campos personalizados:**

| Campo | Tipo | Valores |
|---|---|---|
| Order Date | data | — |
| Order number | **enum** | `#JBXAB`, `#M6IQU`, … e lixo: `email`, `emial`, `wpp Italo`, `KJCBE` |
| **Status** | enum | Standby → Select → Design Pending → Awaiting Measurements → Design Under Client Review → Order sent to Usman → In Production → In Transit → Delivered (+ Canceled) |
| Obs | enum | 2 suits · 6 suits · Criar invoice · Invoice enviar · Invoice pago · Pagamento realizado ao fornecedor |
| Fornecedor | enum | Usman · Manzoor · WheelDeal |
| Pedido | texto | — |
| Responsável | **texto** (não é campo de pessoa) | sempre vazio |

**Checklist do pedido de macacão** (seção-modelo, 7 itens):
conferir pagamento do cliente · solicitar medidas · solicitar design ·
conferir design antes de enviar ao cliente (design, cores, nome,
bandeira, logo) · cobrar status do fornecedor · enviar endereço e pedir
tracking number · regras de "Estrutura do design" (logos de
patrocinadores AZ/Allure/Canotops/Alphaline, nome no cinto, bandeira no
ombro a 45°, logo Alphaline na gola e ombros).

Há também `Sample_FIA 8877-2022`: checklist de homologação FIA do
macacão de kart (6 itens: materiais, cobertura, conforto, testes,
etiqueta FIA, design/logos).

---

## 3. Shipping Orders — pedidos e rastreio

40 tarefas (37 abertas). Owner: Eduardo Resende.
**Seções:** Order Created · Shipped · Arrived · Pending/Needs review ·
Cancelled · Alphaline Suits · Cannotops · Locations.

**Campos personalizados:**

| Campo | Tipo | Valores |
|---|---|---|
| Supplier | enum | KartSport · Comet Kart · Aim · Ebay · Amazon · Alphaline · Cannotops · Etsy · Outro |
| Order Number | texto | — |
| Tracking Number | texto | — |
| Created at | data | — |
| Tipo de pedido | multi-enum | Urace Store Venda/Compra · Suits Venda · Cannotops Venda · Ebay Venda · Dropshipping · Outro |
| **Status da ordem** | enum | Order Created · Shipped · Arrived · Pending/Review · Payment pending · Refunded · Cancelled |

O fluxo é o mesmo padrão dos outros: a tarefa **anda pelas seções**
conforme o status muda.

---

## 4. ADM URACE — SOMENTE LEITURA

1.242 tarefas (87 abertas). **Seções por pessoa:** Klaus · LARA ·
Eduardo · ITALO · Anabelly · ADM · Tarefas de acompanhamento · Samira ·
Canotops · Melhorias/Automatizações · Manu · brainstorming.
Campos: Data de Início (data), Prioridade (Alta/Média/Baixa).

Conteúdo observado: calendário de pagamentos recorrentes (freelancers
toda terça · Hernan dia 10 e 25 · comissões dia 5 · time online dia 27 ·
cartão BOFA), estornos, cobranças que precisam de atenção, e
brainstorming estratégico (expansão para Jacksonville, e-commerce,
motores e pneus). Existe até uma tarefa chamada "Agente autonomo de ia
ADM" na seção do Eduardo.

**Regra:** o Admin AI apenas enxerga este projeto, como contexto. Não
cria, não move, não edita. Revisão só depois de Shipping Orders.

---

## Padrão comum aos 3 projetos operacionais (a chave da automação)

Os três funcionam do mesmo jeito: **um modelo de tarefa + campos a
preencher + a tarefa andando entre quadros**. O estado de um item é
representado DUAS vezes — no campo de status e na seção onde a tarefa
está. Manter os dois em sincronia é parte do trabalho (e é onde a
operação manual escorrega).

| Projeto | Entidade | "Motor" do estado | Quadro (seção) |
|---|---|---|---|
| U-RACE | serviço / corrida | 12 ou 25 subtarefas | dia da semana / RACES |
| SUITS | pedido de macacão | campo Status (10 estados) | Order / Standby |
| Shipping Orders | pedido/envio | campo Status da ordem (7) | Order Created → Shipped → Arrived |

## Inconsistências encontradas — documentadas, NÃO corrigidas

1. **SUITS `Order number` é enum usado como texto livre.** Entre as
   opções: `email`, `emial` (erro de digitação virou opção permanente),
   `wpp Italo`, `KJCBE` (sem `#`). Todos os pedidos recentes estão com
   esse campo vazio. Deveria ser campo de texto.
2. **SUITS: tarefa marcada como concluída com status "In Production" ou
   "In Transit"** (Ferrier_Tim Hannen, Alex_Racing Suit, Mike Speed,
   Mariano). O check de conclusão não significa pedido entregue.
3. **SUITS `Responsável` é campo de TEXTO e está sempre vazio** — não dá
   para saber quem toca cada pedido pelo campo.
4. **Shipping Orders: `Order Number` guardando URL gigante do Alibaba** e
   `Tracking Number` guardando link de portal em vez do código de
   rastreio. Isso quebra qualquer rastreio automático.
5. **Seção × campo de status podem divergir** (o mesmo estado escrito em
   dois lugares). Precisa de uma regra: qual dos dois é a verdade?
6. **A descrição do serviço varia de formato** — um tem rótulos
   ("Driver's name:", "Age:"), outro só valores soltos ("53 inches / 64
   lbs / 10 years old"). Extração é trabalho de interpretação (Claude),
   não de regex.
7. **U-RACE: corrida futura marcada como concluída** significando "não
   vamos" (padrão observado em F4, Lucas Oil, "NOT GOING"). Semântica a
   confirmar com o dono.
8. Dois projetos com o mesmo nome "Silveira Logistics"; "Business
   development" existe como projeto separado do ADM URACE.

## Perguntas em aberto para a explicação de operação

1. Quando estado e quadro divergem, qual vence?
2. Quem é o responsável padrão de cada tipo (serviço, macacão, envio)?
3. Concluir a tarefa significa o quê em cada projeto?
4. O que dispara a criação de cada tarefa (venda fechada, e-mail, pedido
   do cliente, compra feita)?

</details>
