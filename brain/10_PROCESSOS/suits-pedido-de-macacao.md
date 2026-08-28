---
tipo: processo
area: SUITS
fonte: humano
ditado_por: Italo Silveira
data: 2026-08-28
asana_projeto: "1205661933760052"
modelo_de_tarefa: "1217959088745716"
---

# Processo — pedido de macacão (SUITS)

O macacão é **100% personalizado**: medidas, design, cores, logos e a
posição de cada logo são feitos para aquele cliente. Nada é padrão.

## O caminho, do contato à entrega

1. **Contato e negociação** — cliente procura, negocia. (humano)
2. **Pagamento confirmado.**
3. **Formulário de tamanhos** enviado ao cliente. São **29 medidas**;
   junto pede-se ideia de mockup, quais logos e **onde cada logo vai**.
4. **Cliente devolve** medidas + referências de design.
5. **Designer trabalha.** Recebe **só as informações de design** — nunca
   dados de pedido, pagamento ou contato do cliente.
6. **Vai e vem** designer ↔ URACE ↔ cliente até aprovar. **Continua
   humano** por decisão do dono, para manter a qualidade do atendimento.
   Automatizar só depois que o resto estiver rodando.
7. **Design final aprovado** → anexo na tarefa + status `Order sent to
   Usman` → **dispara o e-mail ao fornecedor** (ver gatilho).
8. **1 dia depois** → status vira `In Production`.
9. **Fornecedor avisa no WhatsApp** que despachou → `In Transit`.
10. **Entregue** → `Delivered`.

## Os status e quem os move

| Status | Significa | Quem move |
|---|---|---|
| `Standby` | ordem criada | IA |
| `Awaiting Measurements` | esperando o cliente mandar as medidas | IA |
| `Design Pending` | pagamento confirmado e o cliente já passou as informações de design | IA |
| `Design Under Client Review` | cliente revisando o design do nosso designer | **humano** |
| `Order sent to Usman` | design final anexado; **gatilho do e-mail** | IA |
| `In Production` | 1 dia após o e-mail ao fornecedor | IA |
| `In Transit` | fornecedor avisou no WhatsApp que enviou | IA (a partir do aviso humano) |
| `Delivered` | finalizado | IA |
| `Canceled` | — | humano |

## O gatilho (a automação central)

**Anexo do design final na tarefa + status `Order sent to Usman`** →
enviar o e-mail do pedido ao fornecedor.

Não é um ou outro: são **as duas condições juntas**. Anexo sem o status,
ou status sem anexo, não dispara.

### O e-mail ao fornecedor — formato exato, já em uso

- **Para:** `Speedinds@gmail.com` (Usman — confirmado: respondeu de lá
  assinando "Usman"). ⚠️ Outro fornecedor usa `whitesoldier205@gmail.com`
  — **falta confirmar qual dos três é** (Manzoor ou WheelDeal).
- **Assunto:** `SUIT - {Nome do Cliente}`
- **Anexo:** PDF do design final
- **Corpo:**

```
Hi Usman,

We have a new order:

1 – Head circumference — 59 cm / 1'11"
2 – Distance from forehead to neck — 42 cm / 1'5"
... (as 29 medidas, nesta ordem, sempre em cm / pés-polegadas)
29 – Foot size — 42 EUR / 9 US

Best regards,
{assinatura de quem envia}
```

Cada medida vai em **dupla unidade** (métrica e imperial). O item `6bis`
só aparece para mulheres. **Manter o formato como está** — é o que o
fornecedor já sabe ler.

## O modelo de tarefa

Antes de 28/08 **não existia** modelo de descrição para pedido de
macacão. Criado em `📋 MODELO — New Order: <nome do cliente>`
(gid `1217959088745716`, seção "Checklist para o pedido de macacão").

Nome da tarefa: `New Order: {nome do cliente}`. A descrição tem quatro
blocos: **CLIENTE** (nome, telefone, e-mail, datas), **MEDIDAS** (as 29,
na ordem do e-mail do fornecedor — copiar e colar direto), **DESIGN** (o
que vai para o designer) e **CONTROLE** (fornecedor, anexo, envio).

A separação DESIGN × resto é proposital: é o bloco DESIGN, e só ele, que
vai para o designer.

## Como a IA fica sabendo de um pedido novo

O dono avisa que há pedido novo. A IA então **pede os dados de contato do
cliente** (nome, telefone, e-mail), cria a tarefa `New Order: {cliente}`
com o modelo e, a partir do contato, **procura o cliente pedindo o
formulário de medidas**, explicando que são necessárias porque o macacão
é totalmente personalizado.

## ⚠️ Exceção pedida à regra "a IA não envia e-mail"

Este processo pede que a IA **envie** dois e-mails de verdade: o pedido
de medidas ao cliente e o pedido de produção ao fornecedor. Isso
contraria a regra geral registrada em 28/08 ("a IA nunca envia e-mail, só
cria rascunho"). **Pendente de confirmação explícita do dono** — até lá,
os dois saem como **rascunho**, prontos para envio humano.
