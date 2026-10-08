---
tipo: processo
area: SUITS
fonte: humano
ditado_por: Italo Silveira
data: 2026-08-28
asana_projeto: "1205661933760052"
modelo_de_tarefa: "1217959088745716"
tipo_info: PROCESS
responsavel: Italo Silveira
status: ativo
---

# Processo — pedido de macacão (SUITS)

[[URACE]] · [[Asana]] · [[Gmail]] · fornecedor atual: [[Usman]] · valores em [[PARAMETROS]]

O macacão é **100% personalizado**: medidas, design, cores, logos e a
posição de cada logo são feitos para aquele cliente. Nada é padrão.

## 🔁 Desde 08/10/2026: a aba Suits e a ponte de e-mail (#153)

O pedido de macacão vive na aba **Suits · Alpha Line** do Command Center (não mais no
quadro SUITS do Asana, que foi importado para lá): dez etapas, nota com print em qualquer
etapa, as 29 medidas em cm/pol, design, leads e fornecedores.

A **ponte de e-mail** roda o fluxo que o Ítalo montou no ChatGPT (áudio de 08/10):
venda de macacão no site → a IA agradece, manda o manual de medidas (PDF) e pede o design
→ o cliente responde → a IA grava medidas e design e passa **só o design** ao designer
(Matheus), sem nome completo, e-mail, telefone, endereço ou pagamento do cliente → o designer
pergunta ou entrega a arte → a IA leva ao cliente **sem os dados do designer**. Também lê o
marcador `Suits` e as respostas do fornecedor.

Ítalo: *"eu pedi para tudo passar por minha aprovação por isso que eu fui o gargalo"*. Por
isso a ponte manda **sem aprovação** quando o "envio automático" está ligado. Começa em
**simulação**: o e-mail que a IA mandaria aparece na linha do tempo do pedido para a equipe
conferir, e só depois se liga o envio.

Quem decide o destinatário é o painel (o cliente, o designer ou o fornecedor DAQUELE pedido),
nunca o modelo.

**Do robô do Ítalo (Mio, contexto de 08/10, #156)**:
- **Designer: Mateus** (`carvalhovisual1@gmail.com`). É designer, **não** fabricante. Não se
  apresenta ao cliente, e o cliente nunca recebe o contato, a assinatura, o texto, a conversa ou
  os metadados dele. A arte sai para o cliente sem o nome dele no arquivo e sem EXIF/autor.
- **Quem assina com o cliente: George**, com a assinatura da URACE do Eduardo trocando só o nome
  (sem inventar sobrenome, telefone ou endereço).
- **Política dos macacões**, nas boas-vindas dos pedidos novos e sujeita aos termos da compra e
  aos direitos do cliente:
  - três rodadas de revisão do design antes da produção, sem custo;
  - personalizado não tem devolução voluntária nem reembolso;
  - erro da URACE: corrigido sem custo;
  - erro de medida do cliente que inutilize o macacão: 50% de desconto na troca;
  - erro do design fornecido pelo cliente: 33% de desconto na troca.

  Conflito com os termos ou os direitos do cliente sobe para a equipe.
- **Ryan Casner, pedido #4738**: as boas-vindas (agradecimento + manual) saíram em 28/09
  às 08h41 ET, pelo Eduardo. Não repetir nem mandar adendo de política; a próxima resposta dele
  é com o George. O que a tabela abaixo diz sobre "continua humano" no vai e vem do design foi
substituído por esta decisão.

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
- **Anexo:** **exatamente o mesmo arquivo que está anexado na tarefa do
  pedido no Asana** — o design final. A IA não gera, não escolhe outro e
  não remonta: pega o anexo da tarefa e manda aquele.
  Como: `get_attachments` na tarefa → baixar pelo `download_url` →
  anexar ao e-mail (o Gmail aceita anexo até 25 MB somados).
  Mais de um anexo na tarefa → **não adivinhar**: perguntar qual é o
  design final.
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

## ✅ Exceção AUTORIZADA à regra "a IA não envia e-mail"

Confirmado pelo dono em 28/08: a regra "a IA nunca envia e-mail" vale
para **os outros e-mails** (triagem da inbox, respostas gerais). Neste
processo a IA **envia de verdade**, em duas situações e só nelas:

| ✅ Pode enviar | Para quem |
|---|---|
| Pedido do formulário de medidas | cliente do macacão |
| Pedido de produção (as 29 medidas + PDF) | fornecedor atual |

Qualquer outro e-mail continua sendo **só rascunho**.

## Fornecedor: sempre o atual, lido dos parâmetros

O destinatário **nunca é fixo na skill** — sai de
`brain/00_SYSTEM/PARAMETROS.md`, linha "Fornecedor ATUAL" (hoje: Usman,
`Speedinds@gmail.com`). Trocou de fornecedor, troca-se lá e a IA passa a
mandar para o novo sem mexer em mais nada.
