---
tipo: processo
area: QuickBooks
fonte: humano
ditado_por: Italo Silveira
data: 2026-08-31
---

# Processo — invoice e estimate no [[QuickBooks]]

[[URACE]] · [[Asana]] · [[Gmail]] · [[Security deposit]]

## 🚫 A regra que manda em tudo

**A IA cria e SALVA. A IA NÃO ENVIA.** A invoice fica com status pendente
esperando [[Italo Silveira]] ou [[Eduardo Resende]] revisar e enviar.

Só envia quando um dos dois disser **explicitamente** "pode enviar" /
"envie diretamente" **para aquele cliente**. Autorização de um caso não
vale para o próximo.

Exceção única já autorizada: a invoice do [[Security deposit]] (valor
fixo US$ 400) — ver [[PARAMETROS]].

## Estimate × Invoice

| Documento | Quando |
|---|---|
| **Estimate** (orçamento) | cliente pediu orçamento · **preparação de corrida** (pré-corrida) |
| **Invoice** | serviço realizado · peças · coaching, daily, Urace Academy, dia de equipe, mensal |

## Onde achar o cliente

**Customer Hub → Customers and Leads.** Busca por nome ou e-mail. Na
página do cliente estão **nome, e-mail e telefone** — o necessário para
enviar. (Pela API: `qbo_contact_search_customer`.)

## Campos da invoice

| Campo | Regra |
|---|---|
| Número | gerado pelo QuickBooks |
| Invoice date | data de emissão |
| **Due date** | **2 a 3 dias depois** da invoice date |
| **Service date** (por linha) | dia do serviço / dia em que as peças foram usadas, **conforme agendado no [[Asana]]**. Não é obrigatório, mas **sempre preencher** |
| Produto/serviço | usar os itens que **já existem**. Ver [[QuickBooks]] — só ~25 faturam de verdade |
| Descrição | nem todo item tem. A IA pode escrever — **será revisada por humano** |
| Quantidade e valor | valores de serviço saem do próprio catálogo |

### Classe / tag

| Tipo | Classe |
|---|---|
| Prática / treino | prática |
| Peças | peças |
| Corrida | tag da corrida (existem várias) |
| **Urace Academy** | **entra como corrida** |
| Suits · Canotops | a sua |
| **Security deposit ($400)** | **depósito** |

Corrida sem tag → **criar a tag** e usar.

> ⚠️ **A ferramenta MCP de invoice NÃO tem campo de classe/tag.** Ver a
> pendência técnica no fim deste documento.

### Mensagem na invoice

Normalmente vazia. Quando tem, o padrão é `tipo | detalhe`, minúsculo:

```
parts | partes usadas nas práticas do dia 12/09
training | dias 12, 26 de setembro
race | AMR Round 8 | <datas>
```

O mesmo texto é repetido no outro campo de mensagem.

## Preço de peça — 15% de margem

Alguns preços estão no [[QuickBooks]]. A maioria **não**: a URACE é
dealer oficial e busca o preço da peça no site do fornecedor
([[KartSport]], [[Comet Kart]] etc.) — **da peça exata, para aquele
chassi e aquele motor daquele cliente**. Trabalho manual hoje.

**Sobre o preço encontrado, aplica-se +15%** e é esse valor que vai na
invoice.

## A IA precisa cruzar fontes antes de faturar

As mensagens que chegam trazem **pouca informação**. Antes de montar uma
invoice de peças, a IA consulta o [[Asana]] (e o [[Gmail]]) para saber
**qual chassi e qual motor** aquele cliente usou — a peça tem que ser
compatível com o equipamento daquele treino.

Peça errada na invoice = retrabalho e desgaste com o cliente. Se não
achar chassi/motor, **não adivinhar: perguntar**.

## Pré-corrida (estimate)

Leva as **datas da corrida e as datas de treino**, e **sempre 2 sets de
pneu inclusos**.

### O regulamento manda

A IA **lê o regulamento de cada corrida** e verifica se **pneu e gasolina
têm de ser comprados na pista**:
- se sim, são comprados para **treino oficial e corrida** (sábado e domingo);
- **quinta e sexta** são treinos nossos — a URACE fornece e **cobra à parte**
  (gasolina de treino).

Logística: normalmente compra-se o pneu e envia-se para o local da
corrida; com antecedência dá para retirar na pista. Em corridas com
parceria [[KartSport]], compra-se para retirar lá.

Cobrança: os 2 sets de pneu são cobrados do cliente (a equipe compra por
ele no local) — e o **mecânico** também é cobrado.

## Escalação da invoice pronta

Salvou → **a invoice já tem link**. Mandar no canal de escalação:

```
Invoice para <cliente>
E-mail: <email>   ·   Telefone: <telefone>
Em aguardo para revisão e envio.
<link da invoice>
```

Resposta "ok, pode enviar" / "tudo certo" → **aí sim envia**.
Qualquer outra coisa = ajuste; a IA corrige e reenvia para revisão.

Esse canal é também onde a IA **aprende**: instrução dada ali que virar
regra é gravada aqui ou em [[PARAMETROS]] — ver [[Stand-by e escalação]].

## Rotina de cobrança

- **A cada 2 dias:** selecionar as invoices em aberto e **enviar reminder**.
- **Passou de 30 dias em aberto:** o cliente entra na lista de devedores
  do segundo cérebro, com o valor e há quantos dias — a IA precisa ter
  isso na memória, não só no relatório.

> ⚠️ Hoje há **US$ 185.887 em aberto**, sendo 84% em duas invoices de 2025
> ([[QuickBooks]]). E atenção: **invoice em aberto ≠ inadimplência** —
> existe parcelamento (ex.: 4× US$ 1.000).

## Como a IA pergunta

O dono foi explícito: **ela não tira dúvida sobre tudo.** Tem que
entender, e quando perguntar, ser **concisa e certeira**. Pergunta vaga
ou óbvia queima a confiança do canal.

---

## ⚠️ Pendências técnicas descobertas em 31/08

**1. Classe/tag não existe na ferramenta MCP.** `qbo_sales_create_invoice`
aceita cliente, linhas, `service_date` por linha, `due_date`,
`note_to_customer`, referência, desconto e termos — **mas não tem campo
de classe nem de tag**, e não há ferramenta para criar tag.
Ou a classificação fica para o humano na revisão, ou depende da REST API
com token ([[Etapa de conexão]]).

**2. O reminder exige confirmação a cada envio.** A ferramenta de
lembrete obriga mostrar o texto e **pedir "sim" explícito antes de
disparar**. A rotina "a cada 2 dias, todas as em aberto" precisa de uma
autorização permanente do dono ou de um "ok" por lote.

**3. O que a IA consegue preencher sozinha hoje:** cliente, itens,
quantidades, valores, descrições, `service_date` por linha, `due_date`
(2–3 dias) e a mensagem no padrão `tipo | detalhe`. Salvar sem enviar:
sim. **Classe: não.**
