# Diagnóstico dos serviços de agosto — MIGRADO

Este documento foi **migrado para o segundo cérebro** em 31/08/2026, na
construção do Cérebro Central. O conteúdo vive agora em:

- `brain/13_PROBLEMAS/` — os 7 achados viraram notas de problema, uma cada:
  P-01, P-02, P-03, P-05 e P-10 (resolvido)

O arquivo original fica aqui como registro do que foi levantado na
época. **A fonte de verdade é o vault** — se divergir, o vault vence.

---

<details>
<summary>Conteúdo original (28/08/2026)</summary>

# Diagnóstico dos serviços recentes — U-RACE

Escopo pedido pelo dono: **último mês** (vencimento de 25/07 a 29/08/2026),
porque tarefas antigas carregam erro humano demais para servir de
referência. **31 serviços** analisados. Leitura apenas — nada corrigido
sem autorização; o que exigia atenção virou comentário na tarefa.

## O que está BEM

- **Campo `Race`: 100% preenchido** nas 31 tarefas do período (Practice
  OKC, Practice Bushnell, KART, F4). O identificador que o dono chamou de
  imprescindível está sendo respeitado.
- **Responsável definido**: todos os serviços com Luis Barros.
- **Link de invoice presente** em 27 das 31.

## O que precisa de atenção

### 1. Erro de dado de cliente — e-mail trocado (RISCO REAL)

As três tarefas de *Tyron Brouta_Summer Camp 3 Days* (1/3, 2/3, 3/3)
trazem `Lareau.shaun@gmail.com` como e-mail do responsável. Esse e-mail é
do **Shaun Lareau**, responsável da **Amelyia Lareau** — outro cliente,
do Summer Camp anterior. O responsável do Tyron é **Mathias Brouta**.

Cópia de tarefa sem trocar o campo. Se ninguém pegar, o waiver, a invoice
e a devolução do depósito vão para a família errada.
→ **Comentado nas tarefas 1/3 e 3/3. Não corrigi: falta o e-mail certo.**

### 2. Modelo antigo (8 subtarefas em vez de 12) — 6 tarefas

Amelyia Lareau (4/5 e 5/5) · Andrew Afong · Tyron Brouta (1/3, 2/3, 3/3).
Perdem as subtarefas de checklist e de pós-venda.

### 3. Sem modelo nenhum — 2 tarefas

As duas *Jude Cook* (22 e 23/08): só o link da invoice, **zero
subtarefas**, e estão na coluna **RACES** apesar de serem serviço
(mecânico, motor, chassi). Deveriam estar na coluna do dia.

### 4. Modelo colado, campos em branco — 9 tarefas

Brody Robbin (×2) · Harley Keeble (1/3, 2/3, 3/3) · Jude cook/Harley
client (1/3, 2/3, 3/3) · Alexander Jacoby. Nome do piloto, idade, peso,
altura, responsável, e-mail e telefone: tudo vazio. Do jeito que está, a
IA não tem como decidir waiver de menor ou de adulto — falta a idade.

Casos parciais: *Alex Xikis* (campo "Driver's name" vazio, mesmo com o
nome no título) e *Bryan Santiago* (e-mail gravado como
`Email%3APabloSantiago@outlook.com` — sobrou codificação de URL colada).

### 5. Security deposit quase não aparece — 1 em 31

Só *Jayden Lago* tem a linha `Security deposit: <link> Price: $400` na
descrição. *Noah el Gouchi* tem um segundo link de US$ 400 rotulado como
"Invoice link" (provavelmente é o depósito, mal rotulado). Nas outras 29
não há registro de depósito na descrição.

Como a subtarefa 2 manda **conferir no QuickBooks antes de enviar**, isso
pode significar duas coisas bem diferentes: ou o depósito não foi
cobrado, ou foi cobrado e não registrado na tarefa. Só o QuickBooks
responde — é a primeira coisa a cruzar quando essa automação entrar.

### 6. Colunas dos dias com serviço velho — 10 tarefas

Serviços já concluídos e com data vencida continuam ocupando WEDNESDAY,
THURSDAY, FRIDAY, SATURDAY e SUNDAY (de 05/08 a 23/08). Como as colunas
são a semana, o quadro vai empilhando semanas antigas.
→ **Pergunta ao dono:** serviço concluído sai da coluna do dia? Para
"Finished Services", ou some do quadro? (Regra descrita: *Finished
Services* = data passada **com subtarefas pendentes** — não cobre o caso
do serviço 100% concluído.)

### 7. Datas de corrida — conferir o dia de chegada

Pela regra ditada (equipe chega 2 dias antes do primeiro dia do evento),
as quatro corridas AMR abertas começam **um dia depois** do previsto:

| Corrida | `start_on` atual | Corrida (due) |
|---|---|---|
| AMR R8 Homestead | 17/09 (qui) | 20/09 (dom) |
| AMR R9 | 22/10 (qui) | 25/10 (dom) |
| AMR R10 | 19/11 (qui) | 22/11 (dom) |
| AMR R11 | 17/12 (qui) | 20/12 (dom) |

**Não alterei — depende de um fato que só vocês sabem:** se o evento AMR
roda sexta/sábado/domingo, falta o dia de chegada (deveria começar na
quarta). Se roda só sábado/domingo, as datas estão certas como estão.
Confirmar uma vez e eu aplico o padrão em todas.

## Resumo

| Achado | Quantas |
|---|---|
| E-mail de outro cliente | 3 |
| Modelo antigo (8 subtarefas) | 6 |
| Sem modelo (0 subtarefas) | 2 |
| Modelo em branco | 9 |
| Sem security deposit registrado | 30 |
| Serviço concluído ocupando coluna de dia | 10 |
| Campo `Race` faltando | **0** ✅ |

</details>
