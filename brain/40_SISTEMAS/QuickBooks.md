---
tipo: sistema
fonte: quickbooks
atualizado_em: 2026-08-31
---

# QuickBooks

URACE · realm `9341453113046421`. **A verdade sobre dinheiro está aqui.**
Foi ele que, em 28/08, resolveu sozinho o valor do pacote do
[[Michael Nicholas|Elijah]] e explicou por que não cobrar o depósito dele.

## Papel na operação
- Pagamento de invoice **cria a tarefa** de serviço no [[Asana]]
- Dispara o [[Security deposit]] — ver [[Pagamento e security deposit]]
- Devolução do depósito pelo *merchant view*
- Antes de cobrar depósito: **conferir aqui se já foi cobrado e se foi devolvido**

## ⚠️ O preço NÃO sai daqui

O catálogo do QBO tem **preço defasado**. A fonte de verdade é a
[[Rate Card]] — ver a ordem de precedência em [[PARAMETROS]]. Sempre
comparar o valor lançado contra o `unit_price` do catálogo e **listar a
diferença** no relato.

## Armadilhas do conector (confirmadas em uso)

| Armadilha | Consequência |
|---|---|
| Conta está no nome do **responsável**, não do piloto | buscar o piloto e criar cliente duplicado — ver [[Clientes]] |
| **`doc_number` duplicados nesta conta** | deep link tem que usar `txnId`, nunca o número do documento |
| `amount` da linha é **valor unitário** | `qty 2` + `amount 21.25` = $42,50, não $21,25 |
| **Não aceita dois-pontos** no `Name` do item | `Parts IAME:X` falha; item nasce fora da categoria |
| **Não tem campo de classe nem de tag** | classificação vai como lembrete na escalação |
| **Não edita preço nem inativa item** | só cria e busca; lote só por CSV com "sobrescrever por match exato" |
| Reminder **exige confirmação a cada envio** | rotina de cobrança não é autônoma hoje |

## O catálogo é grande, o uso é pequeno

896 itens cadastrados (360 serviços, 536 peças) — mas **só ~25 realmente
faturam**. É esse conjunto pequeno que a automação precisa conhecer:

| Item | Receita no ano |
|---|---|
| National Event Team Fee | $49.500 |
| Professional Coaching | $31.602 |
| Local Event \| Team Fee | $26.788 |
| Exclusive Mechanic Support | $26.600 |
| Exclusive mechanic support \| National | $25.050 |
| Lead and follow 2 Stroke | $15.765 |
| Used chassi | $13.700 |
| Custom Kart Suit | $13.291 |
| Urace Academy Training Program + Tuner | $9.600 |
| Urace Academy - Racing Program + Tuner | $9.600 |
| 125cc / 100cc Engine Rental \| National Event | $8.000 / $7.600 |
| MG SH2 Red Tires · Evinco Tires | $7.888 / $7.354 |
| Professional Coaching Junior/Senior 2T | $7.271 |
| Summer Camp Micro/Mini 2T · Coaching Mini/Micro | $6.695 / $6.690 |

⚠️ **Cuidado com o relatório por produto:** ele soma $1,09 milhão, mas
inclui as categorias-pai (`Service`, `Parts`, `Rental`, `Karts`) junto
com os filhos — é dupla contagem. A **receita real do ano é US$ 478.094**
(relatório por cliente, 94 clientes).

## Contas a receber — 31/08/2026

**US$ 185.887 em aberto, 29 invoices.** Mas a concentração é extrema:

| Cliente | Em aberto | Situação |
|---|---|---|
| **Juan Pacino** | **$101.445** | vencida em **31/10/2025** — 10 meses |
| **Stephen Collins** | **$55.070** | vencida em **01/12/2025** — 9 meses |
| Todos os outros 27 | $29.372 | — |

As duas primeiras são **84% de tudo que a URACE tem a receber**.

Outros em aberto: [[Leandro Cesar]] (parcelado 4× $1.000, vencendo
05/06, 07/07, 07/08 e 07/09 — mais $4.697 e $1.060) · Frankie Iadevaia
(4 invoices, $2.956) · Gerald White ($3.494) · Silveira Logistics
($3.696) · Kaluah ($1.582) · Lewis Cook ($1.660).

**Tony Peterson de Oliveira: $400 vencendo em 23/09** — pelo valor, é um
[[Security deposit]] emitido e ainda não pago.

## Descobertas que respondem perguntas do projeto

**1. Serviço vendido e não pago É visível.** A pergunta era como a IA
enxergaria um serviço agendado sem pagamento, já que a tarefa do [[Asana]]
só nasce quando a invoice é paga. Resposta: **pelo A/R aging** — invoice
emitida com saldo em aberto é exatamente isso. É essa a fonte para a
regra "enviar o depósito em D-4, pago ou não".

**2. Existe parcelamento.** [[Leandro Cesar]] tem 4 invoices de $1.000
com vencimentos mensais. A automação não pode tratar "invoice em aberto"
como sinônimo de inadimplência — pode ser parcela a vencer.

## Ainda em aberto com o dono

- Como a IA descobre **datas e duração** do serviço a partir do pagamento
- Mapeamento **serviço → item do catálogo** ao preparar invoice
- O que entra na **Pre race invoice** × **After race invoice**
- Devolução do depósito: a IA executa ou só prepara? (*merchant view* é tela)
- Preço das **peças do Service Order**: sai do catálogo ou é digitado?
