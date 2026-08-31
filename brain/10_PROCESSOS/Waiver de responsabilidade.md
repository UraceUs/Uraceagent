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

## Quando assina

1. A IA vê o envelope virar `completed` no [[DocuSign]].
2. Baixa o PDF (`listEnvelopeDocuments`).
3. **Anexa na tarefa do [[Asana]]** daquele serviço.
4. Marca a subtarefa **"Signed waiver?"**.
5. Registra no comentário da tarefa: quem assinou, quando, e o id do
   envelope — chave externa, para nunca duplicar.

O e-mail de confirmação chega no `support@`, mas **não é dele que a IA
depende** — a DocuSign é a fonte. Ver [[DocuSign]].

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
