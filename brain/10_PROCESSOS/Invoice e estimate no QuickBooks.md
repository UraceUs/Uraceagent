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

> ⚠️ **A ferramenta MCP de invoice não tem campo de classe/tag.**
> Decisão do dono (31/08): a IA **escreve na mensagem de escalação um
> lembrete** de qual tag e qual classe aplicar. Quem revisa aplica no
> clique. A IA nunca deixa passar em branco sem avisar.

### Mensagem na invoice

Padrão real (confirmado pelo dono, 31/08) — **`TIPO | SUBTIPO | EVENTO`**:

```
RACE | Pre Race | AMR RD 6&7
Parts | AMR RD 6&7
```

**O mesmo texto vai nos dois campos de mensagem.** Não é minúsculo: é
`RACE` em caixa alta e `Parts` capitalizado, como nos exemplos.

## Preço de peça — 15% de margem

Alguns preços estão no [[QuickBooks]]. A maioria **não**: a URACE é
dealer oficial e busca o preço da peça no site do fornecedor
([[KartSport]], [[Comet Kart]] etc.) — **da peça exata, para aquele
chassi e aquele motor daquele cliente**. Trabalho manual hoje.

**Sobre o preço encontrado, aplica-se +15% — por peça, sempre.** Valor
em [[PARAMETROS]] (é lá que se altera, não aqui).

## Como a IA descobre qual peça cobrar

As mensagens que chegam trazem **pouca informação**. A IA tem **três
caminhos** para chegar na peça certa, e usa todos antes de perguntar:

1. **A própria peça tem referência** — dá para saber para qual chassi e
   qual motor ela serve.
2. **Histórico do [[QuickBooks]]** — muitas peças são usadas com
   frequência; o que já foi faturado antes ensina o padrão.
3. **[[Asana]] e [[Gmail]]** — qual chassi e qual motor aquele cliente
   usou naquele treino.

Só depois de esgotar os três é que pergunta. **A peça tem que ser
compatível com o equipamento daquele cliente** — peça errada na invoice é
retrabalho e desgaste.

## 🔑 O que a mensagem de gatilho precisa ter

Para a IA montar uma invoice, a mensagem que pede tem que trazer
**o nome ou o e-mail do cliente** — é a chave que permite localizá-lo
**no [[QuickBooks]] e no [[Asana]] ao mesmo tempo**. Sem isso ela não
consegue cruzar as fontes; pede o identificador antes de qualquer coisa.

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

⚠️ Lembrete ao revisar: aplicar TAG <tag> e CLASSE <classe>
   (a IA não consegue preencher esses dois campos)
```

Resposta "ok, pode enviar" / "tudo certo" → **aí sim envia**.
Qualquer outra coisa = ajuste; a IA corrige e reenvia para revisão.

Esse canal é também onde a IA **aprende**: instrução dada ali que virar
regra é gravada aqui ou em [[PARAMETROS]] — ver [[Stand-by e escalação]].

## Rotina de cobrança

- **A cada 2 dias:** enviar reminder **somente das invoices OVERDUE**
  (vencidas). Parcela a vencer **não** entra — existe parcelamento, e
  cobrar cliente em dia queima a relação.
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

**2. O reminder exige confirmação a cada envio.** A ferramenta obriga
mostrar o texto e pedir "sim" antes de disparar. Escopo fechado pelo
dono: **a cada 2 dias, só as OVERDUE**. Falta ele decidir se dá
autorização permanente para essa rotina ou aprova por lote.

**3. O que a IA consegue preencher sozinha hoje:** cliente, itens,
quantidades, valores, descrições, `service_date` por linha, `due_date`
(2–3 dias) e a mensagem no padrão `TIPO | SUBTIPO | EVENTO`. Salvar sem
enviar: sim. **Classe e tag: não** — vão como lembrete na escalação.
