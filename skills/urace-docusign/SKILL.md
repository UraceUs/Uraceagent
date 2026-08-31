---
name: urace-docusign
description: Cuida das waivers de responsabilidade da URACE.US INC no DocuSign — o documento que libera o piloto a entrar na pista. Use sempre que o pedido envolver waiver, termo de responsabilidade, parental consent, adult waiver, assinatura de documento, envelope do DocuSign, "quem falta assinar", "manda a waiver para fulano", conferir se um piloto já tem waiver válida, ou a varredura diária de pendências de assinatura. Também aplicável a NDA e Service Agreement que estejam na mesma conta.
---

# Waivers da URACE no DocuSign

Conta `4261a166-3a91-4fb7-97c5-30257d657c52`, titular Italo Jorge da
Silveira, e-mail da conta **`support@urace.us`**, região `na4`.

A waiver é condição para o piloto entrar na pista. Sem ela assinada o
serviço não acontece — por isso a varredura é **diária**.

> **Segundo cérebro.** Prazos e IDs moram em
> `brain/00_SYSTEM/PARAMETROS.md`; o processo em
> `brain/10_PROCESSOS/Waiver de responsabilidade.md`; os fatos da conta em
> `brain/40_SISTEMAS/DocuSign.md`. Ler antes, escrever depois (comentário
> na tarefa do Asana + linha no diário).

## 🚦 O que pode e o que não pode

**A IA ENVIA a waiver** — autorizado pelo Italo em 31/08. É exceção
explícita à regra "a IA não manda e-mail".

| Ação | Permissão |
|---|---|
| Ler status, listar pendentes, montar o alerta diário | ✅ livre |
| Baixar PDF assinado e anexar no Asana | ✅ livre |
| Marcar subtarefa "Signed waiver?" e comentar | ✅ livre |
| **Enviar waiver** (`createEnvelopeFromTemplate`) | ✅ **autorizado**, com as 4 travas abaixo |
| **Lembrete** (`sendReminder`) | ⏳ **não decidido** — alertar o Italo, não o cliente |
| `voidEnvelope`, editar template, mexer em NDA/Service Agreement | 🚫 nunca sem pedido explícito |

### ⚠️ As 4 travas antes de cada envio

`createEnvelopeFromTemplate` **cria e ENVIA no mesmo passo** — chamar a
ferramenta **é** mandar o e-mail, e **não tem volta**. Checar as quatro,
sempre:

1. **Já existe waiver válida?** `completed` daquele signatário com menos
   de 1 ano → **não manda**, marca a subtarefa e segue.
2. **Já existe envelope em aberto?** `sent` ou `delivered` para o mesmo
   signatário → **não manda outro** (é o "não mandar duas vezes").
3. **Idade confirmada?** É ela que escolhe o template. Sem idade
   confirmada, **escalar** — parental para adulto é erro visível.
4. **Nome e e-mail conferidos** contra Asana/QuickBooks. Contato salvo
   no DocuSign com e-mail errado propaga o erro para sempre.

Falhou alguma → **escalar em vez de enviar**: "fulano precisa de waiver
parental, e-mail X, serviço dia Y — confirma?"

**Depois de enviar, registrar:** comentário na tarefa do Asana com
template usado, signatário, e-mail e `envelopeId`, e linha no diário.

## Os dois templates — a idade decide

| Piloto | Template | ID | Vai para |
|---|---|---|---|
| **Menor** | Parental consent Waiver liability | `6dbf2094-39da-4c21-95dd-feda7ac28022` | pai / mãe / responsável |
| **Maior** | Adult Waiver of Liability | `c51aede4-bba5-40df-9f14-24c340e2bd3e` | o próprio piloto |

**Escolher SEMPRE pelo ID.** Há dois templates vazios na conta
(`63dcf553-…`, `5441b464-…`: sem nome, 0 páginas). O dono decidiu em
31/08 que **não serão usados e não serão apagados** — então eles
continuam lá, e com `autoMatch: true` no Parental, escolher por nome ou
deixar o auto-match decidir pode cair no template errado.
**Para a automação existem só os dois IDs da tabela.**

Role dos dois: `Parental Consent Waiver Liability`.

## Antes de mandar: procurar se já existe

**A waiver vale 1 ano a partir da assinatura** — é o que o próprio
e-mail promete ao cliente. Procurar nos dois lugares antes de pedir
outra:

1. **DocuSign** — envelopes `completed` daquele signatário (fonte de verdade)
2. **Asana** — anexos de tarefas anteriores do mesmo piloto

Achou válida? **Não manda outra.** Marca a subtarefa e segue.

⚠️ **O signatário é o RESPONSÁVEL, não o piloto** — mesma armadilha do
QuickBooks. Procurar pelo nome do piloto e não achar **não significa**
que não existe.

## Mandar: dois campos só

**Nome** e **e-mail** do signatário. O DocuSign guarda contatos
anteriores — **conferir os dois sempre**, porque contato salvo com
e-mail errado propaga o erro para todos os envios seguintes.

## Status: `delivered` NÃO é assinado

`created` → `sent` (enviado, nunca aberto) → `delivered` (**abriu e não
assinou**) → `completed` (assinado) · `declined` · `voided`

`delivered` é o estado que mais engana. **Só `completed` conta.**

## 🔁 Varredura diária

`getEnvelopes` com `status: "sent,delivered"`, depois `listRecipients`
em cada um para ter nome e e-mail. Cruzar com o Asana:

| Situação | Ação |
|---|---|
| Serviço a **> 2 dias** | acompanha, sem barulho |
| Serviço a **≤ 2 dias** | **alerta** (prazo de PARAMETROS) |
| Serviço **hoje ou amanhã** sem waiver | **alerta vermelho**, escala na hora |
| Sem serviço agendado | lista, sem urgência |
| Envelope perto de `expireDateTime` | avisa — expirou, reenvia do zero |

O alerta **se repete enquanto o prazo estiver apertado**. É a exceção à
regra de não repetir: prazo que chega **volta a alertar**.

## Quando vira `completed`

Destino: **o arquivo assinado vai para os anexos da tarefa DA CRIANÇA no
Asana, e a subtarefa "Signed waiver?" é marcada como concluída.**

1. `listEnvelopeDocuments` → baixa o PDF assinado.
   **Buscar na DocuSign, não no e-mail** — a conta é a `support@`, então
   o PDF vem da fonte, com `envelopeId` e certificado junto. (A IA não
   tem a caixa `support@`; o anexo do e-mail é caminho alternativo para
   quando ela tiver.)
2. **Mapear signatário → piloto.** Na parental, quem assina é o
   pai/mãe/responsável, mas **a tarefa é da criança**. Nunca procurar a
   tarefa pelo nome do signatário. Mais de uma tarefa do mesmo piloto? A
   do **serviço mais próximo ainda sem waiver**. Sem vínculo claro:
   **escalar, não chutar.**
3. **Anexar o PDF** na tarefa — ⛔ **o conector do Asana não sobe
   arquivo** (só tem `get_attachments`, verificado em 31/08). Precisa do
   Personal Access Token + REST `POST /attachments`. Até lá, pular este
   passo e **comentar com o link** do documento assinado.
4. **Marcar a subtarefa "Signed waiver?" como concluída** —
   `update_tasks` com `completed: true`. **Isto já funciona hoje.**
5. Comentar na tarefa: quem assinou, quando, o `envelopeId` e o link.
   O `envelopeId` é a chave externa que impede duplicar.

> Resumo do que trava e do que não trava: **marcar a subtarefa funciona
> hoje; só o upload do arquivo espera o token do Asana.** Não deixar de
> marcar por causa do anexo.

## Não é só waiver

A conta também tem **NDA** e **Service Agreement**. A varredura os lista
**à parte** e não age sobre eles.

## O texto do Adult Waiver fica como está

O `emailBlurb` do Adult Waiver é cópia do parental — fala em *"your
child's participation"*. **O dono decidiu em 31/08 não mexer.** Não é
pendência, é escolha. Não sinalizar de novo, não sugerir correção, e
**nunca editar template**.
