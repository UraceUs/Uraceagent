---
name: urace-faturamento-qbo
description: Monta invoices e estimates no QuickBooks Online para a URACE.US INC (escola e equipe de kart em Orlando). Use sempre que o pedido envolver faturar cliente ou piloto, cobrar corrida, treino, coaching, aluguel de motor ou chassi, rebuild de motor, peças, combustível, suits ou barracas Canotops, montar orçamento, cobrar invoice vencida, ou quando aparecerem nomes de pilotos (Bryan Santiago, Alex Xikis, Brody Robins, Frankie Iadevaia, Elijah Nicholas), números de invoice no formato 4YZRN1QWN###NQM, ou pedidos como "monte uma invoice", "faz um estimate", "cobra o cliente X". Também aplicável a auditoria de catálogo, correção de preços e conferência de faturas já criadas no QBO.
---

# Faturamento URACE no QuickBooks Online

Empresa: URACE.US INC, [[Orlando Kart Center]]. Conta QBO id
`9341453113046421`.

A cobrança da URACE tem armadilhas que não são óbvias no conector: o
cliente quase nunca está no nome do piloto, o catálogo tem preços
defasados, e há `doc_number` duplicados. Esta skill existe para que uma
fatura saia certa na primeira tentativa e para que **nada seja enviado ao
cliente sem autorização**.

> **Segundo cérebro.** Valores, prazos e IDs **não moram aqui** — moram em
> `brain/00_SYSTEM/PARAMETROS.md`. O processo completo está em
> `brain/10_PROCESSOS/Invoice e estimate no QuickBooks.md`, o preço em
> `brain/40_SISTEMAS/Rate Card.md` e o mapa piloto→conta em
> `brain/20_ENTIDADES/Clientes.md`. Mudou lá, mudou aqui. **Ler antes de
> faturar** e **escrever o que aconteceu depois** (diário + comentário na
> tarefa do Asana).

## ✅ O que esta skill PODE criar

**Criar invoice, estimate, cliente e item de catálogo: pode** — é o
trabalho dela (confirmado pelo Italo em 31/08). A linha não é entre ler e
escrever, é entre **escrever e ENVIAR**.

Não pode: **enviar** invoice (exceto a do security deposit), enviar
estimate ou disparar reminder sem o "ok"; e não apaga, não inativa e não
altera o que já existe.

Antes de criar cliente, buscar pelo responsável e pelo e-mail (tabela
abaixo). Antes de criar item, `qbo_catalog_search_products` — só criar o
que voltar `found: false`.

## 🚫 As duas regras que mandam em tudo

1. **A IA cria e SALVA. A IA NÃO ENVIA.** Fatura criada não é fatura
   enviada. Nunca chamar `qbo_sales_send_invoice` sem instrução
   explícita, para aquele cliente, naquele caso. O Italo frequentemente
   pede a criação justamente para revisar antes. Autorização de um caso
   **não vale** para o próximo.
   **Exceção única já autorizada:** a invoice do security deposit (valor
   fixo, ver PARAMETROS).
2. **Nunca inventar.** Sem fonte, escalar — não deduzir. Preencher lacuna
   com padrão plausível é pior que perguntar, porque vira regra de fato
   na próxima fatura.

## Fluxo obrigatório

Nesta ordem. Pular etapas produz duplicata de cliente ou de item.

1. `company_info` — estabelece a conexão. **Sempre primeiro.**
2. `qbo_contact_search_customer` — ver o mapeamento abaixo **antes** de
   concluir que o cliente não existe.
3. Preço: **Rate Card primeiro** (ver precedência abaixo).
4. `qbo_catalog_search_products` — buscar todos os itens de uma vez
   (aceita até 20 termos).
5. `qbo_catalog_create_product` para cada item com `found: false`.
6. `qbo_sales_create_invoice` ou `qbo_sales_create_estimate`.
7. Reportar ao Italo com divergências e premissas explícitas.

## O que a mensagem de gatilho precisa ter

**Nome ou e-mail do cliente.** É a chave que permite localizá-lo no
QuickBooks e no Asana ao mesmo tempo. Sem isso, pedir o identificador
antes de qualquer coisa.

## Cliente

O registro no QBO está no nome do **responsável financeiro**, não do
piloto. Confirmar por busca antes de usar qualquer id.

| Piloto | Conta no QBO | E-mail | id |
|---|---|---|---|
| Bryan Santiago | Pablo Santiago | pablosantiago@outlook.com | 485 |
| Alex Xikis | James Xikis | james@xikis.com | 352 |
| Brody Robins | Jill Robins | hawaiicampers@gmail.com | — |
| Lewis Cook | Lewis Cook | Lewis.cook@catapultprint.com | 694 |
| Velocity Racing (Rick) | Velocity Racing | rick@velocityracing.com | 675 |
| Elijah Nicholas | Michael Nicholas | — | — |

Buscar pelo e-mail funciona quando o nome não bate. Só criar cliente novo
depois de tentar os dois.

## Preço — ordem de precedência

1. **Valor que o Italo passar** — vence tudo. Usar e **sinalizar a
   divergência**, sem corrigir por conta própria.
2. **Rate Card** — Google Sheet `160efDlmavKKGbtGfJKCTOV_3Q9JEO3Lc6xA1mEMMNyo`
   ("URACE RATE CARD 2026"), **acima do catálogo do QBO**. Canotops tem
   tabela própria: doc `1bIVVEVqloBH4yWqrECODplAX8eQ9u3Mrz_byQ5TRM58`.
   A planilha é documento vivo — **reler, não confiar em cópia**. A aba
   final tem a lista normalizada `Item | Category | Unit | Price | Notes`.
3. **Invoice anterior do mesmo serviço/cliente** — aceitável e economiza
   trabalho, mas dizer explicitamente: *"reaproveitei os valores da
   invoice X"*.
4. **Catálogo do QBO** — preços defasados. Sempre comparar o valor
   lançado contra o `unit_price` retornado na busca e **listar as
   diferenças no relato final**.

**Nunca cotar preço de memória.** Peça sem valor informado entra a `0`
para o Italo preencher, informando quais têm preço no catálogo.

### Regras de preço que a Rate Card fixa

- **Taxa de pista nunca entra na invoice** — paga direto na pista, pelo
  link. Nunca vender como "all inclusive".
- Peça comprada pelo cliente (não pela URACE): **+50% na mão de obra**.
- Peça comprada pela URACE: **+15% por peça** (ver PARAMETROS).
- Segundo motor: **40%** do aluguel do motor.
- Campeonato: **entrada de 30% + parcelas**, quitado antes da última corrida.
- Mecânico varia ±$50 e começa **1 dia antes** do evento.
- Piloto Pro capaz de vencer local: 50% off no team fee local. Piloto em
  2 categorias paga 50% na segunda.

## Criação de item

- **O QBO não aceita dois-pontos no campo `Name`.** `Parts IAME:X` falha.
  Criar com nome simples e avisar que o item nasceu fora da categoria e
  precisa ser movido à mão.
- `taxable: false` é o padrão desta conta.
- `product_type: "SERVICE"` mesmo para peças, seguindo o catálogo existente.
- Preço desconhecido entra como `unit_price: 0`.

## Linhas da fatura

- **`amount` é o valor unitário, não o total da linha.** `quantity: 2` +
  `amount: 21.25` = linha de $42,50.
- `service_date` vai **por linha**, formato `YYYY-MM-DD`, e é o dia do
  serviço conforme agendado no Asana. Não é obrigatório pelo QBO, mas
  **sempre preencher**. Se o Italo não deu a data, deixar em branco e perguntar.
- **Descrição em inglês** — é texto que o cliente lê.
- "x 2 dias" vira `quantity: 2`, **não** duas linhas.
- `due_date`: **2 a 3 dias** depois da data da invoice.
- Mensagem (nos **dois** campos, mesmo texto), padrão `TIPO | SUBTIPO | EVENTO`:
  ```
  RACE | Pre Race | AMR RD 6&7
  Parts | AMR RD 6&7
  ```

### Classe e tag — a IA não consegue preencher

`qbo_sales_create_invoice` **não tem campo de classe nem de tag**, e não
há ferramenta para criar tag. Então a IA **escreve o lembrete na
escalação** e quem revisa aplica no clique. Nunca deixar passar em branco
sem avisar.

| Tipo | Classe |
|---|---|
| Prática / treino | prática |
| Peças | peças |
| Corrida | tag da corrida |
| Urace Academy | **entra como corrida** |
| Suits · Canotops | a sua |
| Security deposit | depósito |

## Como descobrir qual peça cobrar

As mensagens trazem pouca informação. **Três caminhos, todos antes de perguntar:**

1. **A referência da própria peça** diz para qual chassi e motor ela serve.
2. **Histórico do QBO** — muitas peças se repetem; o que já foi faturado
   ensina o padrão.
3. **Asana e Gmail** — qual chassi e motor aquele cliente usou naquele treino.

A peça tem que ser **compatível com o equipamento daquele cliente**.

## Ambiguidade no catálogo

`requires_clarification: true` aparece com frequência e nem sempre exige parar.

- **Match claro pela marca ou motor** → escolher e declarar. Motor KA100 é
  IAME, então "IAME Front Sprocket Z10" é a escolha certa para "front gear Z10".
- **Peças genuinamente diferentes** → escolher a mais provável, criar mesmo
  assim, e sinalizar a alternativa com preço. Ex.: "IAME Reed petal" $21,25
  contra "IAME Fiberglass Reed Petal" $21,89.
- **Item de pacote fechado contra mão de obra avulsa** → nunca sobrescrever.
  "Engine rebuild top end KA100" está a $650 como pacote; cobrar $250 de mão
  de obra nele distorce o item. Sugerir item separado.

Bloquear a tarefa inteira por uma peça de $20 custa mais que sinalizar bem.

## Estimate (orçamento e pré-corrida)

Estimate para: cliente pediu orçamento, e **preparação de corrida**.
Invoice para: serviço realizado, peças, coaching, daily, Urace Academy.

A Rate Card traz **modelo de estimate pronto** (`EST-YYYYMM-NNN`): Client
· Company · Email · Phone · Class · Program · Address · Event Dates,
linhas `Item · Description · Unit · Qty · Unit Price · Total`, Subtotal,
Discount, Tax, **Deposit Due 30%**, Balance Due, TERMS & NOTES,
assinaturas. Linhas padrão: Team fee · Mechanic · Chassis · Engine ·
**Tires — Set** · Fuel · Misc.

Pré-corrida leva as datas da corrida **e** as de treino, e **sempre 2 sets
de pneu**. A IA **lê o regulamento da corrida** para saber se pneu e
gasolina têm de ser comprados na pista — se sim, para treino oficial e
corrida (sáb/dom); quinta e sexta são treinos nossos, cobrados à parte.
O mecânico também é cobrado.

## Identificadores e links

- Reference number: `4YZRN1QWN###NQM`, `5YZRN1QWN###NQM`, `6YZRN1QWN###NQM`.
- **Existem `doc_number` duplicados nesta conta.** Deep link usa sempre
  `txnId`, nunca `doc_number`.
- Formato:
  `https://qbo.intuit.com/app/login?pagereq=invoice%3FtxnId%3D{txnId}&deeplinkcompanyid=9341453113046421`
- **Reproduzir o link do resultado da ferramenta literalmente.** Nunca
  montar um link inventando o id.

## Limitações do conector

- Não edita preço de item existente. Não inativa item. Só cria e busca.
- Atualização de preço em lote sai por CSV: Settings > Import data >
  Products and services, com a opção de **sobrescrever por match exato de
  nome** marcada. Sem essa opção o QBO cria duplicata em vez de atualizar.
- O CSV precisa da coluna **Income Account** preenchida ou mapeada na tela
  de importação. O conector não lê o plano de contas — esse campo fica com
  o Italo.
- Os nomes no CSV precisam bater com o campo `Name` (sem o prefixo de
  categoria), senão vira item novo.
- **Não existe campo de classe nem de tag** (ver acima).

## Cobrança de invoice vencida

- **A cada 2 dias**, reminder **somente das invoices OVERDUE**. Parcela a
  vencer **não** entra: existe parcelamento na conta, e cobrar cliente em
  dia queima a relação. **Invoice em aberto ≠ inadimplência.**
- **Aprovação por lote, sempre.** Não existe autorização permanente para
  esta rotina (decisão do Italo, 31/08). Montar o lote, **mostrar a lista**
  (cliente · valor · dias de atraso · link) e **esperar o "ok"**. "Ok" num
  lote não vale para o próximo. `qbo_sales_send_invoice_reminder` também
  exige confirmação a cada envio — a ferramenta e a regra coincidem.
  Sem "ok", o lote fica em stand-by: não repetir o pedido, mas voltar a
  alertar se o prazo apertar.
- Passou de **30 dias** em aberto: o cliente entra na lista de devedores
  do segundo cérebro, com valor e há quantos dias.

## Permuta

Frankie Iadevaia e Brody Robins operam em permuta. A permuta cobre
**apenas serviços não faturados**. Invoice já emitida segue como cobrança
normal e **não deve ser cancelada** por causa do arranjo.

## Como falar com o cliente (playbook comercial)

Vale para descrição de item, mensagem da invoice e qualquer texto que o
cliente lê:

- **"drivers"**, não "clientes" nem "alunos".
- Track fee e pit pass são pagos **direto ao OKC** e **nunca** entram na
  cobrança da URACE.
- **Nunca** usar "all-inclusive".
- O texto do security deposit é **travado** — não reescrever.
- **Nunca** usar a palavra "vandalismo".
- Nunca copiar e colar bloco pronto sem adaptar ao caso.

## Relato ao Italo

Depois de criar, responder assim:

1. Uma linha confirmando cliente e total, com o **link do QBO literal**.
2. A pergunta de próximo passo que o conector devolve (enviar ou ajustar).
3. Os pontos de atenção, cada um em bloco curto e numerado:
   - divergências entre valor lançado e catálogo/Rate Card, com os dois valores
   - premissas assumidas (tamanho, data, qual variante da peça)
   - **lembrete de TAG e CLASSE** a aplicar no clique
   - itens novos criados que precisam ser movidos de categoria
   - o que ficou faltando (service date, decisão pendente)

Português, direto, sem emoji, sem travessão. O Italo corrige em uma
frase; texto longo atrapalha. E ele foi explícito: **a IA não tira dúvida
sobre tudo** — quando perguntar, ser concisa e certeira.

**Perguntar não trava nada.** A resposta não vem na hora: registrar a
pergunta, pôr **aquele item** em stand-by e seguir com o resto. Não
repetir a pergunta, mas **voltar a alertar se o prazo chegar**.

## Não inventar

Sem definição na URACE para: **política de desconto** e **modelo de
e-mail de invoice** (confirmado em 31/08 — não existe). Se o pedido
depender de algum destes, dizer que não está definido e pedir a definição.

> Margem sobre peças (**15%**), **classe/tag**, **prazo de pagamento
> (2-3 dias)** e **frequência de cobrança (2 dias, só overdue)** **já
> foram definidos** pelo Italo em 31/08 e estão acima — versões antigas
> desta skill listavam esses quatro como "sem definição".
