---
name: urace-gmail
description: Triagem diária da caixa urace@urace.us — lê cada e-mail novo, classifica com os marcadores existentes, cria rascunho de resposta (nunca envia), alimenta o quadro Shipping Orders do Asana com compras e envios, e registra tudo no segundo cérebro. Use na rotina diária de e-mail ou quando precisar classificar/entender um e-mail da URACE.
---

# Triagem da caixa `urace@urace.us`

A taxonomia abaixo foi lida da conta real (130+ marcadores). A caixa está
organizada: **manter, não reinventar.**

## 🚫 Regras invioláveis

1. **NUNCA enviar e-mail.** Só criar rascunho. Enviar é do humano.
2. **Não apagar, não arquivar sem instrução, não marcar spam.**
3. **Na dúvida, perguntar** — generosamente nos primeiros dias.
4. **Tom:** a caixa recebe pedido de orçamento e mensagem de parceiro.
   Responder com calma e cordialidade; a relação vale mais que a pressa.

## Marcadores (o que vai em cada um)

| Marcador | Vai isto |
|---|---|
| **`wNews`** | **toda propaganda**, newsletter, promoção, mala direta. É o que evita o acúmulo. Sub: `wNews/Study` para curso e conteúdo |
| `Finances/Pending Invoices ❗` | invoice/cobrança em aberto que precisa de ação |
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
4. Se pedir resposta → **rascunho**, nunca envio.
5. Dúvida → perguntar.
6. Relatar: quantos e-mails, quais marcadores, o que ficou pendente,
   e registrar no diário do Obsidian (`urace-obsidian`).

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
