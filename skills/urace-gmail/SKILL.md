---
name: urace-gmail
description: Triagem diária das caixas urace@urace.us e support@urace.us — lê cada e-mail novo, classifica com os marcadores existentes, cria rascunho de resposta (nunca envia), alimenta o quadro Shipping Orders do Asana com compras e envios, e registra tudo no segundo cérebro. Use na rotina diária de e-mail ou quando precisar classificar/entender um e-mail da URACE.
---

# Triagem das caixas `urace@urace.us` e `support@urace.us`

A taxonomia abaixo foi lida da conta real (130+ marcadores). A caixa está
organizada: **manter, não reinventar.**

## 🚫 Regras invioláveis

1. **NUNCA enviar e-mail nesta rotina.** Só rascunho — enviar é do
   humano. (As duas únicas exceções autorizadas vivem no processo do
   macacão, não aqui: pedido de medidas ao cliente e pedido de produção
   ao fornecedor. Ver `brain/00_SYSTEM/PARAMETROS.md`.)
2. **Não apagar e não marcar spam.** Arquivar, só propaganda (item 5).
3. **Na dúvida, perguntar** — generosamente nos primeiros dias.
4. **Tom:** a caixa recebe pedido de orçamento e mensagem de parceiro.
   Responder com calma e cordialidade; a relação vale mais que a pressa.
5. **Arquivar só `wNews`.** Propaganda sai da inbox ao ser etiquetada;
   **todo o resto fica visível na inbox**, mesmo já classificado. A IA
   limpa o ruído, não esconde o que precisa de decisão do dono.
6. **Rascunho só para lead/orçamento e cliente atual.** Parceria e
   financeiro o dono responde pessoalmente — a IA classifica e para por
   aí. Nunca enviar, em nenhum dos casos.

## Marcadores (o que vai em cada um)

| Marcador | Vai isto |
|---|---|
| **`wNews`** | **toda propaganda**, newsletter, promoção, mala direta. É o que evita o acúmulo. Sub: `wNews/Study` para curso e conteúdo |
| `Finances/Pending Invoices ❗` | **conta a PAGAR** — o que a URACE deve e está em aberto (fornecedor, serviço, assinatura). Cobrança que a URACE emitiu **não** vai aqui |
| `Finances/QuickBooks` | notificação do QuickBooks (paga, recebida, lembrete) |
| `Finances/Receipt` · `/Purchase refund` | comprovante · reembolso de compra |
| `Finances/Shopping` (+ `/Amazon`, `/Orlando Kart Center`, `/Track Pass`) | compra |
| `Finances/Square` · `/Clover/Invoiss` · `/Tolls` · `/Accounting` | recebimento · faturamento · pedágio · contabilidade |
| `Banks/<banco>` | Bank of America · American Express · PayPal · Robinhood · Stripe · Venmo · Seacoast · Idea Financial |
| `RACES/National/<série>` | SKUSA · USPKS · Star Champions · Supernats · ROK Vegas · ROTAX · CKNA · IAME USA GN |
| `RACES/Local (FL)/<série>` | FLKC · Orlando Cup \| BFO · FWT · AMR Homestead · WKA Daytona · North Florida Kart Club |
| `RACES/F4/<série>` | JFC · Fara · Lucas Oil |
| `Marketing & Sales/Comercial/Formulario do site` | lead que chegou pelo site |
| `Marketing & Sales/Comercial/Leads` · `/Leads por e-mail - acompanhar` | lead e acompanhamento |
| **`Marketing & Sales/Partnership`** | **parceiro** — cuidado redobrado no tom |
| `Kart Racing School \| Client talks` (+ `/Pro Team Urace`) | conversa direta com cliente |
| **`Shipping Status`** | **rastreio e status de envio → alimenta o Asana** |
| `URace Store/Parts_Loja` · `/Purchase` · `/Shipped Orders` · `/Pending order` | loja |
| `Suppliers` (+ `/Stickers - Jake`, `/Mudflap`) | fornecedor |
| `Suits` (+ `/Homologação`) | macacão |
| `Travels/Flights` · `/Hotels Reservation` · `/Car rental/ Uber` · `Flights/Refunds and Travel Credits` | logística de viagem |
| `Team/<pessoa>` | LARA · Samira · Eduardo · Anabelly · `E-mails do Support` |
| `Platforms & Subscriptions/<serviço>` | ASANA · Docusign · Ecwid · Dialpad · ebay · Google · Alibaba · ETSY · LegalShield · simplybook · magicJack · NordVPN |
| `LOC \| Practice/Practice Orlando` · `/Practice Bushnell` | prática por local |
| `CORP/<empresa>` | AZ · Urace Autosales · Canotops · Getavan · Silveira Logistics · Betim |
| `ITALO` (+ `/Pending email`) | pessoal do Italo |
| `Resumes (CVs)` | currículo |

Marcador novo só com autorização — a taxonomia é do time, não da IA.

## Rotina diária

1. Ler cada thread nova da inbox (assunto, remetente, corpo).
2. Classificar e aplicar o marcador. Propaganda → `wNews`.
3. Se for **compra nossa** → atualizar o Asana (abaixo).
4. **Rascunho** se for lead/orçamento ou cliente atual — nunca envio.
   Parceria e financeiro: só classificar, o dono responde.
5. Propaganda etiquetada como `wNews` → **arquivar** (tirar da inbox).
   Qualquer outro e-mail **permanece na inbox**.
6. Dúvida → perguntar.
7. Relatar: quantos e-mails, quais marcadores, quantos arquivados,
   quais rascunhos criados e o que ficou em dúvida — e registrar no
   diário do Obsidian (`urace-obsidian`).

## Waiver assinada → tarefa do Asana

**As waivers assinadas sempre chegam em `support@urace.us`.**

> ⚠️ **Hoje a IA NÃO tem essa caixa** — só a `urace@`, e só vê a support@
> quando a urace@ está em cópia (testado em 28/08). Enquanto isso não for
> resolvido na [[Etapa de conexão]], este fluxo **não funciona**: a IA não
> deve concluir que "não existe waiver" apenas por não achar. O caminho
> alternativo é procurar nos **anexos de tarefas anteriores** do piloto.

Ao encontrar uma waiver na triagem:

1. Identificar **de qual piloto** é (nome no PDF/assunto).
2. Achar a tarefa de serviço dele no U-RACE.
3. **Anexar o PDF na tarefa** e marcar a subtarefa `Signed waiver?`.
4. Etiquetar a thread (`Platforms & Subscriptions/Docusign`).
5. Registrar no diário.

A waiver **vale por temporada**. Antes de pedir uma nova, procurar nos
dois lugares: anexos de tarefas anteriores do piloto **e** a caixa
`support@`. Pedir de novo a quem já assinou é atrito à toa com o cliente.

## Compra → quadro Shipping Orders (`1215968721507536`)

E-mail de pedido feito, envio, atualização de status ou entrega alimenta
a tarefa:

| Campo | O que entra |
|---|---|
| nome da tarefa | nome da peça / item comprado |
| `Supplier` `1215973949234112` | de onde comprou |
| `Order Number` `1215973949234125` | número do pedido |
| `Created at` `1215973949234129` | data da compra |
| `Tracking Number` `1215973949234127` | **link** de rastreio que abre |
| `Status da ordem` `1215973949424917` | Order Created → Shipped → Arrived |
| descrição | previsão de entrega |

**Dedupe pelo número do pedido.** E-mail de atualização do mesmo pedido
**atualiza** a tarefa existente — nunca cria outra. Mover a tarefa para o
quadro correspondente ao status (ver `urace-asana`).

## Armadilhas já vistas nesta caixa

- Link de e-mail (`google.com/url?q=…`) **expira** — guardar o destino real.
- URL de notificação com token de sessão (Alibaba) não serve como link
  estável: extrair o número do pedido e montar o link do portal.
- Código de rastreio solto não é link. `1Z…` é UPS →
  `https://www.ups.com/track?track=yes&trackNums=<código>`.
  Transportadora desconhecida → **não inventar**: escalar.
- Remetente frio se passando por assunto sério (ex.: "taxes owed" de
  domínio aleatório) é propaganda/spam, não `ITALO`.
