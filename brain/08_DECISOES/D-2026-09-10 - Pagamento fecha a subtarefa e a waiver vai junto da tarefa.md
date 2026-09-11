---
tipo: decisao
data: 2026-09-10
fonte: dono (chat, fim de tarde)
tipo_info: DECISION
responsavel: Italo Silveira
status: ativo
---

# D-2026-09-10 — Pagamento confirmado fecha a subtarefa, e toda tarefa criada leva a waiver

**Dono:** *"chegou email confirmando o pagamento do david pera no email e a
ia ainda nao marcou como pago na subtask do asana"* e *"a cada tarefa criada
buscar a waiver do cliente e deixar anexado na tarefa e no card do cliente"*.

## Pagamento → subtarefa

A confirmação que vale é a do **QuickBooks**, não a do e-mail (o e-mail é
aviso; o saldo é o fato). A sincronia compara a invoice com o que havia
antes: saldo que zerou (ou status `paid`) registra o evento `invoice.paid`.
Esse evento **não acorda o agente** — o painel resolve em código:

1. acha a tarefa do serviço pela data no memo (`Service date: MM/DD/AAAA`);
   se não houver, pelo vencimento + 2 dias; senão a tarefa aberta do
   cliente mais próxima daquela data;
2. fecha a subtarefa de pagamento (casa "payment … completed/received",
   "pago", "paid"), sem nunca reabrir nada;
3. comenta na tarefa: `[IA ADM] Pagamento confirmado: invoice X de $Y.
   Subtarefa "…" marcada como concluída.`

Mecânico é de propósito: não gasta crédito da Anthropic, não depende de o
agente estar de pé e não pede aprovação (o dinheiro já entrou).

## Waiver junto da tarefa

A cada tarefa criada — pela IA (na hora, pelo gid) ou vista no quadro
(evento `task.created`) — o painel busca a waiver **assinada e dentro do
ano**, baixa o PDF do DocuSign **uma vez** para `~/.urace/waivers` (600),
anexa na tarefa do Asana e guarda o vínculo. No card do cliente a linha do
serviço mostra "📎 waiver" e o botão de PDF passa a servir o arquivo
guardado (não depende do DocuSign estar de pé). Nunca anexa duas vezes.

As duas coisas aparecem em **Automação** como regra ligável:
"Pagamento confirmado" e "Waiver junto da tarefa".

## Revisão dos processos (o que faltava da palavra do dono)

Relendo tudo o que foi ditado desde 27/08, entrou na memória da IA o que
ainda não estava lá: depósito é **um por cliente** e se confere no QBO
antes de cobrar (28/08); **peça = fornecedor + 15%** (31/08); cobrança de
atrasado é **por lote, só OVERDUE, com "ok" a cada lote** (31/08); **não
existe modelo de e-mail de invoice** — quem envia é o QuickBooks (31/08).

E o furo que o teste real mostrou virou trava: quando o valor da invoice
**não veio do dono nem do catálogo do QuickBooks**, a proposta sai
marcada *"confira o preço antes de aprovar"* com o valor do catálogo ao
lado e o lembrete de qual aba da Rate Card manda (corrida → Racing team;
treino → Academy). Foi assim que os $1.600 de "Training Program + Tuner"
— produto que não existe na Rate Card — passaram batido.

Relacionado: [[D-2026-09-10 - Correcoes do teste real com a extensao]],
[[D-2026-08-31 - Rate Card acima do catalogo do QuickBooks]],
[[D-2026-08-31 - Waiver vale um ano]].
