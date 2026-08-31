---
tipo: parametros
fonte: humano
atualizado_em: 2026-08-28
---

# ⚙️ PARÂMETROS — o que muda com o tempo

[[URACE]] · usado por [[Pedido de macacão]] · [[Pagamento e security deposit]] · [[Triagem de e-mail]] · [[Compra e envio]]

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

## 💵 Valores

| Parâmetro | Valor |
|---|---|
| Security deposit | **US$ 400** |
| **Margem sobre peça** | **+15%** sobre o preço do fornecedor, **por peça** |
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
| Lembrete de cobrança | **a cada 2 dias** — só invoices **overdue** |
| **Envio** da invoice do depósito | **4 dias antes** do serviço (ou **no mesmo dia**, se o serviço foi agendado com menos de 4 dias) |
| **Pagamento** das duas invoices **+ waiver assinada** | **2 dias antes** do serviço |
| Confirmação de corrida antes do evento | 15 dias (organizado: 30) |
| Status `In Production` após e-mail ao fornecedor | **1 dia** |

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
| QuickBooks | URACE · realm `9341453113046421` |

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
