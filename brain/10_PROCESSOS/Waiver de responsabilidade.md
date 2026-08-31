---
tipo: processo
area: DocuSign
fonte: humano
ditado_por: Italo Silveira
data: 2026-08-31
---

# Processo — waiver de responsabilidade

[[URACE]] · [[DocuSign]] · [[Asana]] · [[Clientes]] · [[PARAMETROS]]

A waiver é uma das 12 subtarefas do serviço no [[Asana]] ("Signed
waiver?") e é **condição para o piloto entrar na pista**. Sem ela
assinada, o serviço não acontece — por isso a rotina é diária, não
semanal.

## Qual template

**A idade do piloto decide.**

| Piloto | Template | Vai para |
|---|---|---|
| **Menor de idade** | Parental consent Waiver liability | pai, mãe ou responsável legal |
| **Maior de idade** | Adult Waiver of Liability | o próprio piloto |

IDs em [[DocuSign]] — **escolher sempre pelo ID**, nunca por nome (há
dois templates vazios na conta e o auto-match pode errar).

## Antes de mandar: procurar se já existe

**A waiver vale 1 ano a partir da assinatura** (é o que o próprio e-mail
promete ao cliente). Antes de pedir uma nova, procurar nos dois lugares:

1. **[[DocuSign]]** — envelopes `completed` daquele signatário. É a
   fonte de verdade.
2. **[[Asana]]** — anexos de tarefas anteriores do mesmo piloto.

Achou uma válida (assinada há menos de 1 ano)? **Não manda outra.**
Marca a subtarefa e segue. Mandar duas vezes irrita o cliente e polui a
conta.

⚠️ **Cuidado com o nome.** O signatário é o **responsável**, não o
piloto — a mesma armadilha do [[QuickBooks]] (ver [[Clientes]]). A
waiver do Elijah Nicholas está no nome do responsável, não no dele.

## Como se manda

São **dois campos, só**: **nome** e **e-mail** do signatário. O DocuSign
guarda contatos anteriores — **sempre conferir os dois** antes de enviar,
porque contato salvo com e-mail errado propaga o erro.

## 🔁 Rotina diária — a parte que é da IA

**Todo dia**, a IA varre o [[DocuSign]] e monta a lista de pendentes:

- envelopes com status `sent` (enviado, **nunca aberto**)
- envelopes com status `delivered` (**aberto e não assinado**)

⚠️ `delivered` **não é assinado**. É o estado que mais engana: a pessoa
abriu, leu e deixou pra depois. Só `completed` conta.

Para cada pendente, a IA cruza com o [[Asana]]:

| Situação | Ação |
|---|---|
| Tem serviço agendado e faltam **> 2 dias** | acompanha, sem barulho |
| Tem serviço agendado e faltam **≤ 2 dias** | **alerta** — é o prazo de [[PARAMETROS]] |
| Serviço **amanhã ou hoje** sem waiver | **alerta vermelho**, escala na hora |
| Sem serviço agendado | fica na lista, sem urgência |
| **Envelope perto de expirar** | avisa — waiver expirada tem que ser reenviada do zero |

O alerta **se repete enquanto o prazo estiver apertado** — esta é a
exceção à regra "não repetir pergunta" de [[Stand-by e escalação]]:
prazo que chega **volta a alertar**, sempre.

## Quando assina (regra do dono, 31/08)

O destino é sempre o mesmo: **o arquivo assinado vai para os anexos da
tarefa DA CRIANÇA no [[Asana]], e a subtarefa "Signed waiver?" é marcada
como concluída.**

### 🔀 Achar a tarefa certa: o signatário NÃO é o piloto

Este é o passo que erra fácil. Na waiver parental:

- **quem assina** = o pai/mãe/responsável (é o nome no envelope)
- **de quem é a tarefa** = **a criança**, o piloto

Então a IA **não procura a tarefa pelo nome do signatário**. Ela mapeia
responsável → piloto (mesma tabela de [[Clientes]] que resolve o
[[QuickBooks]]) e só então acha a tarefa. Achou mais de uma tarefa do
mesmo piloto? A do **serviço mais próximo** que ainda está sem waiver.
Não achou o vínculo? **Escala — não chuta.**

### De onde sai o arquivo

O dono descreveu "pegar do e-mail o anexo". São **duas fontes possíveis**,
e hoje só uma funciona:

| Fonte | Estado |
|---|---|
| **[[DocuSign]]** (`listEnvelopeDocuments`) | ✅ **funciona hoje** — a conta é a `support@`, o PDF vem direto da fonte |
| Anexo do e-mail em `support@` | ⛔ a IA **não tem essa caixa** ([[Etapa de conexão]]) |

**Regra: buscar o PDF na DocuSign.** É o mesmo arquivo, com a vantagem de
trazer junto o `envelopeId` e o certificado. O e-mail fica como caminho
alternativo para quando o `support@` existir.

### ⛔ O anexo em si está bloqueado pelo conector

O conector do [[Asana]] tem **`get_attachments` (ler) e nada de escrever**
— não existe ferramenta de subir arquivo. Verificado em 31/08.

Então, **até o token do Asana existir** ([[Etapa de conexão]]), o passo
"anexar" fica assim:

| Passo | Hoje | Com o token (REST `POST /attachments`) |
|---|---|---|
| Achar a tarefa da criança | ✅ | ✅ |
| **Anexar o PDF** | ⛔ **não dá pelo conector** | ✅ |
| Comentar com o link do documento assinado + `envelopeId` | ✅ | ✅ |
| **Marcar "Signed waiver?" como concluída** | ✅ (`update_tasks`, `completed: true`) | ✅ |

Ou seja: **a marcação da subtarefa já funciona hoje**; só o upload do
arquivo espera o token. Enquanto isso a IA comenta na tarefa com o link
do assinado, para o arquivo não ficar invisível.

### A sequência

1. Envelope vira `completed` no [[DocuSign]].
2. `listEnvelopeDocuments` → baixa o PDF assinado.
3. Mapeia **signatário → piloto** e acha a tarefa da criança.
4. **Anexa o PDF** na tarefa (quando o token existir).
5. **Marca a subtarefa "Signed waiver?" como concluída.**
6. Comenta na tarefa: quem assinou, quando, o `envelopeId` e o link —
   chave externa, para nunca duplicar.

## 🚦 O que a IA pode fazer sozinha

> ⚠️ **`createEnvelopeFromTemplate` cria e ENVIA no mesmo passo.** Não
> existe rascunho para revisar depois, como na invoice do
> [[QuickBooks]]. Enviar waiver = mandar e-mail a cliente.

| Ação | Permissão |
|---|---|
| Ler status, listar pendentes, montar o alerta diário | ✅ livre |
| Baixar o PDF assinado e anexar no [[Asana]] | ✅ livre |
| Marcar a subtarefa e comentar | ✅ livre |
| **Enviar waiver nova** (`createEnvelopeFromTemplate`) | ⏳ **aguardando decisão do dono** |
| **Reenviar lembrete** (`sendReminder`) | ⏳ **aguardando decisão do dono** |
| Anular envelope, editar template, mexer em NDA/Service Agreement | 🚫 **nunca sem pedido explícito** |

Até o dono decidir, a IA **prepara e escala**: "fulano precisa de waiver
parental, e-mail X, serviço dia Y — mando?"

## Outros documentos na conta

DocuSign também carrega **NDA** e **Service Agreement** (ex.: Caio
Imperato, Pablo Santiago). **Não são waiver** — a rotina diária os lista
à parte e não age sobre eles.
