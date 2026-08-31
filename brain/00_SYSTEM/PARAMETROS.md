---
tipo: parametros
fonte: humano
atualizado_em: 2026-08-31
---

# ⚙️ PARÂMETROS — o que muda com o tempo

[[URACE]] · usado por [[Pedido de macacão]] · [[Pagamento e security deposit]] · [[Triagem de e-mail]] · [[Compra e envio]] · [[Invoice e estimate no QuickBooks]]

> **ESTE É O ÚNICO LUGAR ONDE SE ALTERA ESTES VALORES.**
> Mudou aqui, mudou em todo lugar. Nenhuma skill, script, prompt ou
> documento repete esses valores — **todos leem daqui**.
> Se você mudar um valor abaixo, a IA passa a operar com o novo na hora,
> sem precisar mexer em mais nada.
>
> **Como alterar:** troque o valor, ajuste a data em `atualizado_em` e
> registre a linha no histórico do fim da página.

---

## 🧵 Fornecedores de macacão (SUITS)

| Papel | Quem | Contato |
|---|---|---|
| **Fornecedor ATUAL** | **Usman** | `Speedinds@gmail.com` |
| Outros cadastrados no Asana | Manzoor · WheelDeal | — |
| ⚠️ e-mail não identificado | `whitesoldier205@gmail.com` | recebeu "SUIT - Frankie Iadevaia"; falta saber a qual fornecedor pertence |

**Regra:** todo pedido vai para o **fornecedor atual** acima. Trocou de
fornecedor? Troque a linha "Fornecedor ATUAL" e a IA passa a mandar para
o novo — sem mexer em skill nenhuma.

## 🎓 Nomes de serviço que mudaram

| Antes | Agora | Item no QuickBooks |
|---|---|---|
| Karting School | **Urace Academy** | `Service:Karting School Junior/Senior 4T` (id 290) ainda tem o nome antigo · `Service:Urace Academy Training Program` (id 177) |

O catálogo do QuickBooks **ainda usa o nome antigo em parte dos itens**.
Ao ler uma invoice antiga, "Karting School" e "Urace Academy" são o
mesmo serviço. Ao emitir, conferir qual item está sendo usado.

## 💰 De onde sai o PREÇO (ordem de precedência)

| # | Fonte | Observação |
|---|---|---|
| 1 | **Valor que o dono passar** | vence tudo. Usar e **sinalizar a divergência** — nunca corrigir por conta própria |
| 2 | **[[Rate Card]]** (Google Sheet) | fonte de verdade acima do catálogo · Canotops tem tabela própria |
| 3 | **Invoice anterior** do mesmo serviço/cliente | aceitável e economiza trabalho, mas **dizer explicitamente**: "reaproveitei os valores da invoice X" |
| 4 | Catálogo do [[QuickBooks]] | **preços defasados** — sempre comparar o lançado contra o `unit_price` e listar a diferença no relato |

**Nunca cotar preço de memória.** Peça sem valor conhecido entra a `0`
para o dono preencher, com aviso de quais têm preço no catálogo.

## 💵 Valores

| Parâmetro | Valor |
|---|---|
| Security deposit | **US$ 400** |
| **Margem sobre peça** | **+15%** sobre o preço do fornecedor, **por peça** |
| Peça comprada pelo cliente (não pela URACE) | **+50% na mão de obra** ([[Rate Card]]) |
| Segundo motor | **40%** do aluguel do motor ([[Rate Card]]) |
| Entrada de campeonato | **30%** + parcelas, quitado antes da última corrida |
| Taxa de pista | **nunca entra na invoice** — paga direto na pista |
| Frequência do depósito | **um por CLIENTE**, enquanto estiver retido |
| Ordem de cobrança | 1º invoice do serviço · 2º depósito (assim que a 1ª for paga — **ou no limite dos 4 dias, pago ou não**) |

### Quando cobrar o depósito (regra do dono, 28/08)

O depósito é uma **retenção ativa**, não uma cobrança por pacote.
Antes de cobrar, a IA **verifica no [[QuickBooks]] se o depósito daquele
cliente foi devolvido**:

| Situação do depósito | Ação |
|---|---|
| Nunca teve | **cobrar** US$ 400 |
| Cobrado e **devolvido/reembolsado** | **cobrar de novo** |
| Cobrado e **ainda retido** | **NÃO cobrar** |
| Não consegue determinar | **não cobrar — escalar** |

Caso real: Elijah Nicholas tem depósito de 15/06/2026 (US$ 400, pago) e
**não devolvido** — por isso os pacotes de julho, agosto e setembro não
levam cobrança nova. Sem essa verificação, seria cobrado 4 vezes.

## 📅 Prazos

| Parâmetro | Valor |
|---|---|
| Chegada da equipe antes do 1º dia do evento | **2 dias** |
| Nosso treino antes do 1º dia do evento | 1 dia |
| Devolução do security deposit após a sessão | **5 dias** |
| Lembrete de cobrança | **a cada 2 dias** — só invoices **overdue**, e **com "ok" do dono a cada lote** |
| **Envio** da invoice do depósito | **4 dias antes** do serviço (ou **no mesmo dia**, se o serviço foi agendado com menos de 4 dias) |
| **Pagamento** das duas invoices **+ waiver assinada** | **2 dias antes** do serviço |
| Confirmação de corrida antes do evento | 15 dias (organizado: 30) |
| Status `In Production` após e-mail ao fornecedor | **1 dia** |
| **Validade da waiver** | **1 ano a partir da assinatura** (é o que o e-mail do [[DocuSign]] promete ao cliente) |

## 🏁 Campo `Race` do Asana (`1213088541600529`)

`Practice OKC` (Orlando — padrão) · `Practice Bushnell` · `KART` ·
`F4` · `TRACK CLOSED`

## 📧 Caixas de e-mail

`urace@urace.us` · `support@urace.us`

### Quando a IA PODE enviar e-mail (exceções autorizadas)

Autorizado pelo dono em 28/08. A regra geral continua sendo **não
enviar** — estas duas situações são a exceção:

| Situação | Para quem |
|---|---|
| ✅ Pedido do formulário de medidas do macacão | cliente do SUITS |
| ✅ Pedido de produção do macacão | fornecedor atual |
| ✅ **Invoice do security deposit** (valor fixo US$ 400) | cliente do serviço |
| 🚫 Invoice do serviço e qualquer outra | **humano envia** |
| 🚫 **Todo o resto** (triagem, respostas da inbox) | **só rascunho** |

## 👥 Quem autoriza

Italo Silveira (`urace@urace.us`) · Eduardo Resende

### Cobrança de invoice vencida — **aprovação POR LOTE**

Decisão do dono (31/08): **não existe autorização permanente** para a
rotina de reminder. A IA monta o lote das invoices **overdue**, mostra a
lista, e **espera o "ok"**. Cada lote, a cada 2 dias, passa por um
humano. "Ok" dado num lote **não vale** para o lote seguinte.

Enquanto o "ok" não vem, o lote fica em stand-by — ver
[[Stand-by e escalação]]. A IA **não repete a cobrança do "ok"**, mas
**volta a alertar se o prazo apertar**.

## 🔗 IDs de sistemas

| O quê | ID |
|---|---|
| Workspace Asana | `1205450084498489` |
| U-RACE | `1205450093098920` |
| SUITS | `1205661933760052` |
| Shipping Orders | `1215968721507536` |
| ADM URACE (só leitura) | `1205530439507169` |
| Modelo de tarefa de macacão | `1217959088745716` |
| Google Calendar de corridas | Urace Race Calendar |
| **Conta DocuSign** (e-mail `support@urace.us`) | `4261a166-3a91-4fb7-97c5-30257d657c52` |
| Template waiver **parental** (menor) | `6dbf2094-39da-4c21-95dd-feda7ac28022` |
| Template waiver **adult** (maior) | `c51aede4-bba5-40df-9f14-24c340e2bd3e` |
| QuickBooks | URACE · realm / company id `9341453113046421` |
| **Rate Card 2026** (planilha) | `160efDlmavKKGbtGfJKCTOV_3Q9JEO3Lc6xA1mEMMNyo` |
| **Canotops Price List** (documento) | `1bIVVEVqloBH4yWqrECODplAX8eQ9u3Mrz_byQ5TRM58` |

## 📍 Endereços

| Uso | Endereço |
|---|---|
| **Cobrança (sempre este)** | 6149 Cyril Ave, Orlando FL 32809 |
| Galpão URACE | 6149 Cyril Ave, Orlando FL 32809 |

---

## Histórico de alterações

| Data | O que mudou | Quem |
|---|---|---|
| 2026-08-28 | Arquivo criado. Fornecedor atual = Usman; depósito US$ 400; exceções de envio de e-mail autorizadas | Italo |
| 2026-08-28 | IA autorizada a **enviar a invoice do depósito** (só ela). Envio 4 dias antes; pagamento de tudo + waiver 2 dias antes | Italo |
| 2026-08-31 | Margem de peça fixada em **+15%**; lembrete de cobrança **a cada 2 dias, só para invoice OVERDUE** | Italo |
| 2026-08-31 | [[DocuSign]] conectado e sondado. Conta é a **`support@`** — o fluxo da waiver deixa de depender da caixa de e-mail. IDs dos 2 templates registrados; validade da waiver fixada em **1 ano da assinatura** | Italo |
| 2026-08-31 | Mensal Academy 4T e Baby Kart corrigidos para **$2.756,90** e sessão extra dos dois para **$689,23** (planilha diz $2.756,00 / $689,00 — 4 células a arrumar, ver [[Rate Card]]). Regra fixada: **sessão extra = mensal ÷ 4**, e **pacote sai do mensal, nunca da unitária**. E-mail de invoice: **sai pelo próprio QuickBooks**, não existe template a escrever | Italo |
| 2026-08-31 | Reminder de cobrança: **aprovação por lote**, sem autorização permanente | Italo |
| 2026-08-31 | [[Rate Card]] passa a ser a fonte de preço **acima do catálogo do QuickBooks**; ordem de precedência registrada. IDs das duas planilhas adicionados | Italo (skill `urace-faturamento-qbo`) |
